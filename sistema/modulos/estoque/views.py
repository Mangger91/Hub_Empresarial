import csv
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import wrap
import unicodedata

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management.base import CommandError
from django.db.models import Case, F, IntegerField, Q, Sum, Value, When
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sistema.models import CategoriaEstoque, ItemEstoque, ModuloSistema, MovimentacaoEstoque
from sistema.permissions import usuario_pode_editar, usuario_tem_acesso

from ..common import MESES_PT_BR, contexto_modulo, renderizar_modulo_sem_permissao
from .forms import (
    CategoriaEstoqueForm,
    ImportarEstoquePlanilhasForm,
    ItemEstoqueForm,
    MovimentacaoEstoqueForm,
    RelatorioEstoqueFiltroForm,
)
from sistema.management.commands.importar_estoque_excel import Command as ImportarEstoqueCommand
from .regras import (
    area_do_modulo_estoque,
    categorias_estoque_por_modulo,
    rota_do_modulo_estoque,
    valores_categorias_estoque_por_modulo,
)


VALOR_ZERO = Decimal("0.00")
PDF_PAGE_WIDTH = 842
PDF_PAGE_HEIGHT = 595
PDF_MARGIN_X = 40
PDF_MARGIN_TOP = 552
PDF_MARGIN_BOTTOM = 48
PDF_LINE_HEIGHT = 14


def _modulo_estoque_ou_404(modulo_codigo):
    try:
        modulo = ModuloSistema(modulo_codigo)
    except ValueError as erro:
        raise Http404("Modulo de estoque nao encontrado.") from erro

    if modulo not in {
        ModuloSistema.ESTOQUE_ADM,
        ModuloSistema.ESTOQUE_TI,
        ModuloSistema.ESTOQUE_EXPEDIENTE,
    }:
        raise Http404("Modulo de estoque nao encontrado.")
    return modulo


def _dados_padrao_relatorio():
    hoje = timezone.localdate()
    return {"periodo": "mes", "mes": hoje.strftime("%Y-%m")}


def _dados_relatorio_com_padrao(query_params):
    dados = _dados_padrao_relatorio()
    if query_params:
        dados.update(query_params.dict())
    return dados


def _titulo_estoque(modulo):
    titulos = {
        ModuloSistema.ESTOQUE_ADM: "Estoque ADM",
        ModuloSistema.ESTOQUE_TI: "Estoque TI",
        ModuloSistema.ESTOQUE_EXPEDIENTE: "Estoque Expediente",
    }
    return titulos[modulo]


def _modulo_por_area_estoque(area):
    modulos_por_area = {
        ItemEstoque.Area.ADMINISTRATIVO: ModuloSistema.ESTOQUE_ADM,
        ItemEstoque.Area.TECNOLOGIA: ModuloSistema.ESTOQUE_TI,
        ItemEstoque.Area.EXPEDIENTE: ModuloSistema.ESTOQUE_EXPEDIENTE,
    }
    return modulos_por_area[area]


def _normalizar_texto_busca(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "").casefold())
    return "".join(caractere for caractere in texto if not unicodedata.combining(caractere))


def _ids_itens_por_busca(area, busca):
    termos = [
        termo
        for termo in (_normalizar_texto_busca(parte) for parte in busca.split())
        if termo
    ]
    if not termos:
        return []

    categorias = {
        categoria.codigo: categoria.nome
        for categoria in CategoriaEstoque.objects.filter(area=area)
    }
    ids = []
    itens = ItemEstoque.objects.filter(area=area).only(
        "id",
        "nome",
        "codigo_proprio",
        "descricao",
        "categoria",
    )
    for item in itens:
        texto_item = _normalizar_texto_busca(
            " ".join(
                [
                    item.nome,
                    item.codigo_proprio,
                    item.descricao,
                    item.categoria,
                    categorias.get(item.categoria, ""),
                ]
            )
        )
        if all(termo in texto_item for termo in termos):
            ids.append(item.pk)
    return ids


def _saldo_movimentacoes_item(item):
    totais = item.movimentacoes.aggregate(
        saldo=Sum(
            Case(
                When(tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA, then=F("quantidade")),
                When(
                    tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
                    then=Value(-1) * (F("quantidade") - F("quantidade_devolvida")),
                ),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
    )
    return totais["saldo"] or 0


def _sincronizar_saldo_item(item):
    saldo_movimentacoes = _saldo_movimentacoes_item(item)
    if item.quantidade_atual != saldo_movimentacoes:
        item.quantidade_atual = saldo_movimentacoes
        item.save(update_fields=["quantidade_atual", "atualizado_em"])
    return saldo_movimentacoes


def _ajustar_saldo_item(item, saldo_desejado, usuario):
    saldo_atual = _sincronizar_saldo_item(item)
    diferenca = saldo_desejado - saldo_atual
    if diferenca == 0:
        return False

    if diferenca > 0:
        tipo = MovimentacaoEstoque.TipoMovimento.ENTRADA
        quantidade = diferenca
    else:
        tipo = MovimentacaoEstoque.TipoMovimento.SAIDA
        quantidade = abs(diferenca)

    MovimentacaoEstoque.objects.create(
        item=item,
        data_movimentacao=timezone.localdate(),
        tipo=tipo,
        quantidade=quantidade,
        quantidade_devolvida=0,
        custo_unitario=item.custo_unitario or VALOR_ZERO,
        setor="Ajuste",
        observacao=(
            "Ajuste manual pela edicao do item: "
            f"saldo alterado de {saldo_atual} para {saldo_desejado}."
        ),
        responsavel=usuario,
    )
    item.refresh_from_db()
    return True


def _categoria_estoque_com_modulo(pk):
    categoria = get_object_or_404(CategoriaEstoque, pk=pk)
    modulo = _modulo_por_area_estoque(categoria.area)
    return categoria, modulo


def _novo_totalizador():
    return {
        "entradas": 0,
        "retiradas": 0,
        "devolvidas": 0,
        "custo_entradas": VALOR_ZERO,
        "custo_retiradas": VALOR_ZERO,
        "movimentos": 0,
    }


def _rotulo_mes(ano, mes):
    return f"{MESES_PT_BR.get(mes, str(mes))}/{ano}"


def _valor_movimentacao(movimentacao):
    return movimentacao.quantidade_liquida * movimentacao.custo_unitario


def _montar_painel_estoque(area):
    itens = list(ItemEstoque.objects.filter(area=area))
    categorias = {
        categoria.codigo: categoria.nome
        for categoria in CategoriaEstoque.objects.filter(area=area)
    }
    resumo_categorias = defaultdict(lambda: {"codigo": "", "nome": "", "itens": 0, "saldo": 0})
    painel = {
        "total_itens": len(itens),
        "saldo_total": 0,
        "valor_estimado": VALOR_ZERO,
        "sem_estoque": 0,
        "baixo_estoque": 0,
        "confortavel": 0,
        "categorias": [],
    }

    for item in itens:
        valor_item = item.quantidade_atual * item.custo_unitario
        painel["saldo_total"] += item.quantidade_atual
        painel["valor_estimado"] += valor_item

        if item.quantidade_atual <= 0:
            painel["sem_estoque"] += 1
        elif item.estoque_minimo > 0 and item.quantidade_atual < item.estoque_minimo:
            painel["baixo_estoque"] += 1
        else:
            painel["confortavel"] += 1

        resumo_categoria = resumo_categorias[item.categoria]
        resumo_categoria["codigo"] = item.categoria
        resumo_categoria["nome"] = categorias.get(item.categoria, item.categoria)
        resumo_categoria["itens"] += 1
        resumo_categoria["saldo"] += item.quantidade_atual

    painel["categorias"] = sorted(
        resumo_categorias.values(),
        key=lambda categoria: (-categoria["itens"], categoria["nome"].lower()),
    )
    return painel


def _formatar_moeda_pdf(valor):
    return f"R$ {_formatar_decimal_csv(valor)}"


def _encurtar_texto(valor, limite):
    texto = " ".join(str(valor or "-").split())
    if len(texto) <= limite:
        return texto
    return f"{texto[: max(0, limite - 3)]}..."


def _escapar_texto_pdf(valor):
    texto = " ".join(str(valor or "").split())
    texto = texto.encode("cp1252", "replace").decode("cp1252")
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _adicionar_texto_pdf(pagina, x, y, texto, tamanho=9, fonte="F1"):
    pagina.append((x, y, texto, tamanho, fonte))


def _nova_pagina_pdf(paginas, estado):
    paginas.append([])
    estado["y"] = PDF_MARGIN_TOP


def _adicionar_linha_relatorio_pdf(
    paginas,
    estado,
    texto,
    tamanho=9,
    fonte="F1",
    recuo=0,
    largura=115,
):
    linhas = wrap(" ".join(str(texto or "").split()), width=largura) or [""]
    for linha in linhas:
        if estado["y"] < PDF_MARGIN_BOTTOM:
            _nova_pagina_pdf(paginas, estado)
        _adicionar_texto_pdf(
            paginas[-1],
            PDF_MARGIN_X + recuo,
            estado["y"],
            linha,
            tamanho=tamanho,
            fonte=fonte,
        )
        estado["y"] -= PDF_LINE_HEIGHT


def _adicionar_espaco_pdf(paginas, estado, altura=8):
    estado["y"] -= altura
    if estado["y"] < PDF_MARGIN_BOTTOM:
        _nova_pagina_pdf(paginas, estado)


def _renderizar_pdf(paginas):
    recursos = (
        b"<< /Font << "
        b"/F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> "
        b"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
        b"/F3 << /Type /Font /Subtype /Type1 /BaseFont /Courier >> "
        b">> >>"
    )
    objetos = [b"", b"", b""]
    ids_paginas = []

    for numero, pagina in enumerate(paginas, start=1):
        _adicionar_texto_pdf(
            pagina,
            PDF_PAGE_WIDTH - 96,
            24,
            f"Pagina {numero}",
            tamanho=8,
            fonte="F1",
        )
        comandos = []
        for x, y, texto, tamanho, fonte in pagina:
            comandos.append(
                f"BT /{fonte} {tamanho} Tf {x:.1f} {y:.1f} Td ({_escapar_texto_pdf(texto)}) Tj ET"
            )
        stream = "\n".join(comandos).encode("cp1252", "replace")
        pagina_id = len(objetos)
        objetos.append(b"")
        conteudo_id = len(objetos)
        objetos.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        objetos[pagina_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_WIDTH} {PDF_PAGE_HEIGHT}] "
            f"/Resources ".encode("ascii")
            + recursos
            + f" /Contents {conteudo_id} 0 R >>".encode("ascii")
        )
        ids_paginas.append(pagina_id)

    objetos[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pagina_id} 0 R" for pagina_id in ids_paginas)
    objetos[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(ids_paginas)} >>".encode("ascii")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    deslocamentos = [0]
    for objeto_id in range(1, len(objetos)):
        deslocamentos.append(len(pdf))
        pdf.extend(f"{objeto_id} 0 obj\n".encode("ascii"))
        pdf.extend(objetos[objeto_id])
        pdf.extend(b"\nendobj\n")

    inicio_xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objetos)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for deslocamento in deslocamentos[1:]:
        pdf.extend(f"{deslocamento:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objetos)} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF".encode(
            "ascii"
        )
    )
    return bytes(pdf)


def _movimentacoes_do_relatorio(area, filtros):
    movimentacoes = MovimentacaoEstoque.objects.select_related("item", "responsavel").filter(
        item__area=area,
        data_movimentacao__range=(filtros["data_inicio"], filtros["data_fim"]),
    )

    if filtros.get("item"):
        movimentacoes = movimentacoes.filter(item=filtros["item"])
    if filtros.get("categoria"):
        movimentacoes = movimentacoes.filter(item__categoria=filtros["categoria"])
    if filtros.get("setor"):
        movimentacoes = movimentacoes.filter(setor__icontains=filtros["setor"])
    if filtros.get("tipo"):
        movimentacoes = movimentacoes.filter(tipo=filtros["tipo"])

    return movimentacoes.order_by("data_movimentacao", "item__nome", "id")


def _montar_relatorio_estoque(movimentacoes, itens_controle=None):
    totais = {
        **_novo_totalizador(),
        "saldo_quantidade": 0,
        "itens_movimentados": 0,
        "custo_total_movimentado": VALOR_ZERO,
    }
    itens_movimentados = set()
    resumo_por_item = {}
    retiradas_por_data = {}
    comparativo_mensal = {}

    for movimentacao in movimentacoes:
        quantidade_liquida = movimentacao.quantidade_liquida
        valor_total = _valor_movimentacao(movimentacao)
        itens_movimentados.add(movimentacao.item_id)
        totais["movimentos"] += 1
        totais["custo_total_movimentado"] += valor_total

        resumo_item = resumo_por_item.setdefault(
            movimentacao.item_id,
            {
                **_novo_totalizador(),
                "item": movimentacao.item,
                "saldo_periodo": 0,
            },
        )
        resumo_item["movimentos"] += 1

        chave_mes = (movimentacao.data_movimentacao.year, movimentacao.data_movimentacao.month)
        resumo_mes = comparativo_mensal.setdefault(
            chave_mes,
            {
                **_novo_totalizador(),
                "ano": chave_mes[0],
                "mes": chave_mes[1],
                "rotulo": _rotulo_mes(chave_mes[0], chave_mes[1]),
            },
        )
        resumo_mes["movimentos"] += 1

        if movimentacao.tipo == MovimentacaoEstoque.TipoMovimento.ENTRADA:
            totais["entradas"] += quantidade_liquida
            totais["custo_entradas"] += valor_total
            totais["saldo_quantidade"] += quantidade_liquida
            resumo_item["entradas"] += quantidade_liquida
            resumo_item["custo_entradas"] += valor_total
            resumo_item["saldo_periodo"] += quantidade_liquida
            resumo_mes["entradas"] += quantidade_liquida
            resumo_mes["custo_entradas"] += valor_total
            continue

        totais["retiradas"] += quantidade_liquida
        totais["devolvidas"] += movimentacao.quantidade_devolvida
        totais["custo_retiradas"] += valor_total
        totais["saldo_quantidade"] -= quantidade_liquida
        resumo_item["retiradas"] += quantidade_liquida
        resumo_item["devolvidas"] += movimentacao.quantidade_devolvida
        resumo_item["custo_retiradas"] += valor_total
        resumo_item["saldo_periodo"] -= quantidade_liquida
        resumo_mes["retiradas"] += quantidade_liquida
        resumo_mes["devolvidas"] += movimentacao.quantidade_devolvida
        resumo_mes["custo_retiradas"] += valor_total

        resumo_dia = retiradas_por_data.setdefault(
            movimentacao.data_movimentacao,
            {
                "data": movimentacao.data_movimentacao,
                "retiradas": 0,
                "devolvidas": 0,
                "custo_retiradas": VALOR_ZERO,
                "movimentos": 0,
            },
        )
        resumo_dia["retiradas"] += quantidade_liquida
        resumo_dia["devolvidas"] += movimentacao.quantidade_devolvida
        resumo_dia["custo_retiradas"] += valor_total
        resumo_dia["movimentos"] += 1

    totais["itens_movimentados"] = len(itens_movimentados)

    resumo_ordenado = sorted(
        resumo_por_item.values(),
        key=lambda item: (
            -item["custo_retiradas"],
            -item["retiradas"],
            item["item"].nome.lower(),
        ),
    )

    itens_controle = itens_controle or []
    tabela_controle = []
    for item in itens_controle:
        resumo_item = resumo_por_item.get(
            item.pk,
            {
                "entradas": 0,
                "retiradas": 0,
                "devolvidas": 0,
                "item": item,
                "saldo_periodo": 0,
            },
        )
        tabela_controle.append(
            {
                "item": item,
                "produto": item.nome,
                "categoria": item.categoria_nome,
                "entradas": resumo_item["entradas"],
                "saidas": resumo_item["retiradas"],
                "estoque_atual": item.quantidade_atual,
            }
        )
    grupos_controle = []
    for categoria_nome in sorted({linha["categoria"] for linha in tabela_controle}):
        grupos_controle.append(
            {
                "titulo": f"CONTROLE DE ESTOQUE {categoria_nome}".upper(),
                "linhas": [
                    linha for linha in tabela_controle if linha["categoria"] == categoria_nome
                ],
            }
        )

    return {
        "totais": totais,
        "resumo_por_item": resumo_ordenado,
        "tabela_controle": tabela_controle,
        "tabelas_controle": grupos_controle,
        "top_retiradas": [item for item in resumo_ordenado if item["retiradas"] > 0][:5],
        "retiradas_por_data": [retiradas_por_data[data] for data in sorted(retiradas_por_data)],
        "comparativo_mensal": [
            comparativo_mensal[chave] for chave in sorted(comparativo_mensal)
        ],
    }


def _formatar_decimal_csv(valor):
    return f"{valor:.2f}".replace(".", ",")


def _texto_pdf(valor):
    return str(valor or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _titulo_controle_estoque(modulo, filtros):
    categoria_codigo = filtros.get("categoria")
    if categoria_codigo:
        categoria_nome = CategoriaEstoque.objects.filter(
            area=area_do_modulo_estoque(modulo),
            codigo=categoria_codigo,
        ).values_list("nome", flat=True).first()
        if categoria_nome:
            return f"Controle de Estoque {categoria_nome}".upper()
    return f"Controle de Estoque {_titulo_estoque(modulo).replace('Estoque ', '')}".upper()


def _itens_controle_estoque(area, filtros):
    itens = ItemEstoque.objects.filter(area=area, ativo=True)
    if filtros.get("item"):
        itens = itens.filter(pk=filtros["item"].pk)
    if filtros.get("categoria"):
        itens = itens.filter(categoria=filtros["categoria"])
    return list(itens.order_by("categoria", "nome"))


def _exportar_relatorio_csv(modulo, filtros, movimentacoes, relatorio):
    nome_arquivo = (
        f"relatorio_estoque_{modulo.value}_{filtros['data_inicio']}_{filtros['data_fim']}.csv"
    )
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    resposta.write("\ufeff")

    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow(["Periodo", filtros["data_inicio"].strftime("%d/%m/%Y"), filtros["data_fim"].strftime("%d/%m/%Y")])
    for tabela in relatorio["tabelas_controle"]:
        escritor.writerow([])
        escritor.writerow([tabela["titulo"]])
        escritor.writerow(["PRODUTOS", "ENTRADAS", "SAIDAS", "ESTOQUE ATUAL"])
        for linha in tabela["linhas"]:
            escritor.writerow(
                [
                    linha["produto"],
                    linha["entradas"],
                    linha["saidas"],
                    linha["estoque_atual"],
                ]
            )

    return resposta


def _exportar_relatorio_pdf(modulo, filtros, movimentacoes, relatorio):
    nome_arquivo = (
        f"relatorio_estoque_{modulo.value}_{filtros['data_inicio']}_{filtros['data_fim']}.pdf"
    )
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
        title="Relatorio de estoque",
    )
    estilos = getSampleStyleSheet()
    produto_style = ParagraphStyle(
        "ProdutoTabela",
        parent=estilos["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=9,
        spaceBefore=0,
        spaceAfter=0,
    )
    titulo_tabela_style = ParagraphStyle(
        "TituloTabelaEstoque",
        parent=estilos["BodyText"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        textColor=colors.HexColor("#111827"),
    )
    periodo_style = ParagraphStyle(
        "PeriodoRelatorio",
        parent=estilos["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#374151"),
    )
    numero_style = ParagraphStyle(
        "NumeroTabela",
        parent=estilos["BodyText"],
        alignment=TA_CENTER,
        fontName="Helvetica",
        fontSize=8,
        leading=9,
    )
    numero_destaque_style = ParagraphStyle(
        "NumeroDestaqueTabela",
        parent=numero_style,
        fontName="Helvetica-Bold",
    )

    conteudo = [
        Paragraph(
            f"Periodo: {filtros['data_inicio'].strftime('%d/%m/%Y')} a {filtros['data_fim'].strftime('%d/%m/%Y')}",
            periodo_style,
        ),
        Spacer(1, 0.18 * cm),
    ]

    largura_total = landscape(A4)[0] - documento.leftMargin - documento.rightMargin
    colunas = [largura_total * 0.52, largura_total * 0.15, largura_total * 0.15, largura_total * 0.18]

    if relatorio["tabelas_controle"]:
        for tabela in relatorio["tabelas_controle"]:
            dados = [
                [Paragraph(_texto_pdf(tabela["titulo"]), titulo_tabela_style), "", "", ""],
                ["PRODUTOS", "ENTRADAS", "SAÍDAS", "ESTOQUE ATUAL"],
            ]
            for linha in tabela["linhas"]:
                dados.append(
                    [
                        Paragraph(_texto_pdf(linha["produto"]).upper(), produto_style),
                        Paragraph(str(linha["entradas"]), numero_style),
                        Paragraph(str(linha["saidas"]), numero_style),
                        Paragraph(str(linha["estoque_atual"]), numero_destaque_style),
                    ]
                )

            tabela_pdf = LongTable(dados, colWidths=colunas, repeatRows=2)
            tabela_pdf.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, 0), (-1, 0)),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2f3")),
                        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#c7d2f0")),
                        ("TEXTCOLOR", (0, 0), (-1, 1), colors.HexColor("#111827")),
                        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 13),
                        ("FONTSIZE", (0, 1), (-1, 1), 8.5),
                        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#4b5563")),
                        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#111827")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, 0), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                        ("TOPPADDING", (0, 1), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                    ]
                )
            )
            conteudo.append(tabela_pdf)
            conteudo.append(Spacer(1, 0.35 * cm))
    else:
        conteudo.append(
            Table(
                [["Nenhum produto encontrado para os filtros selecionados."]],
                colWidths=[largura_total],
                style=TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#9ca3af")),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("PADDING", (0, 0), (-1, -1), 14),
                    ]
                ),
            )
        )

    def desenhar_rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawRightString(
            landscape(A4)[0] - doc.rightMargin,
            0.55 * cm,
            f"Pagina {doc.page}",
        )
        canvas.restoreState()

    documento.build(conteudo, onFirstPage=desenhar_rodape, onLaterPages=desenhar_rodape)
    resposta = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    return resposta


@login_required
def estoque_adm(request):
    return _estoque(request, ModuloSistema.ESTOQUE_ADM)


@login_required
def estoque_ti(request):
    return _estoque(request, ModuloSistema.ESTOQUE_TI)


@login_required
def estoque_expediente(request):
    return _estoque(request, ModuloSistema.ESTOQUE_EXPEDIENTE)


def _estoque(request, modulo):
    area = area_do_modulo_estoque(modulo)
    titulo = _titulo_estoque(modulo)
    descricao = "Movimentacoes com saldo automatico, historico e alerta de estoque minimo."
    context = contexto_modulo(request, modulo, titulo, descricao)
    itens = ItemEstoque.objects.filter(area=area).annotate(
        total_entradas=Sum(
            Case(
                When(
                    movimentacoes__tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
                    then=F("movimentacoes__quantidade"),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
            default=0,
        ),
        total_saidas=Sum(
            Case(
                When(
                    movimentacoes__tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
                    then=F("movimentacoes__quantidade")
                    - F("movimentacoes__quantidade_devolvida"),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
            default=0,
        ),
    )
    busca = request.GET.get("q", "").strip()
    categoria = request.GET.get("categoria", "").strip()
    status = request.GET.get("status", "").strip()
    categorias_disponiveis = categorias_estoque_por_modulo(modulo)
    categorias_validas = valores_categorias_estoque_por_modulo(modulo)
    itens_criticos = ItemEstoque.objects.filter(area=area).filter(
        Q(quantidade_atual__lte=0)
        | Q(estoque_minimo__gt=0, quantidade_atual__lt=F("estoque_minimo"))
    ).order_by("quantidade_atual", "nome")[:8]

    if busca:
        itens = itens.filter(pk__in=_ids_itens_por_busca(area, busca))
    if categoria and categoria in categorias_validas:
        itens = itens.filter(categoria=categoria)
    elif categoria:
        categoria = ""
    if status == "sem_estoque":
        itens = itens.filter(quantidade_atual__lte=0)
    elif status == "perigoso":
        itens = itens.filter(estoque_minimo__gt=0, quantidade_atual__gt=0, quantidade_atual__lt=F("estoque_minimo"))
    elif status == "confortavel":
        itens = itens.filter(
            Q(estoque_minimo=0, quantidade_atual__gt=0)
            | Q(estoque_minimo__gt=0, quantidade_atual__gte=F("estoque_minimo"))
        )

    context["itens"] = itens
    context["painel_estoque"] = _montar_painel_estoque(area)
    context["total_filtrado"] = itens.count()
    context["itens_criticos"] = itens_criticos
    context["mostrar_acoes"] = usuario_pode_editar(request.user, modulo)
    context["permite_importacao_planilha"] = (
        modulo == ModuloSistema.ESTOQUE_ADM and usuario_pode_editar(request.user, modulo)
    )
    context["filtros"] = {"q": busca, "categoria": categoria, "status": status}
    context["categorias_estoque"] = categorias_disponiveis
    context["categoria_selecionada_label"] = dict(categorias_disponiveis).get(categoria, "")
    return render(request, "sistema/estoque_lista.html", context)


def _salvar_upload_temporario(arquivo, diretorio):
    caminho = Path(diretorio) / arquivo.name
    with caminho.open("wb") as destino:
        for chunk in arquivo.chunks():
            destino.write(chunk)
    return caminho


@login_required
def importar_estoque_adm(request):
    modulo = ModuloSistema.ESTOQUE_ADM
    context = contexto_modulo(
        request,
        modulo,
        "Importar Estoque ADM",
        "Substitua os registros atuais pelas planilhas enviadas.",
    )
    context["rota_estoque"] = rota_do_modulo_estoque(modulo)

    if context["acesso_negado"]:
        context["form"] = ImportarEstoquePlanilhasForm()
        return render(request, "sistema/estoque_importar.html", context)

    if not context["permite_edicao"]:
        messages.error(request, "Seu perfil permite apenas visualizar este estoque.")
        return redirect("estoque_adm")

    if request.method == "POST":
        form = ImportarEstoquePlanilhasForm(request.POST, request.FILES)
        if form.is_valid():
            comando = ImportarEstoqueCommand()
            resumo_total = {
                "itens_excluidos": 0,
                "movimentos_excluidos": 0,
                "itens_criados": 0,
                "itens_atualizados": 0,
                "entradas_criadas": 0,
                "saidas_criadas": 0,
                "movimentos_ignorados": 0,
            }
            arquivos = [
                (form.cleaned_data.get("arquivo_copa"), ItemEstoque.Categoria.COPA),
                (form.cleaned_data.get("arquivo_expediente"), ItemEstoque.Categoria.EXPEDIENTE),
            ]
            try:
                with TemporaryDirectory() as diretorio:
                    if form.cleaned_data.get("substituir_estoque"):
                        movimentos_excluidos, itens_excluidos = comando.substituir_estoque_adm()
                        resumo_total["movimentos_excluidos"] = movimentos_excluidos
                        resumo_total["itens_excluidos"] = itens_excluidos

                    for arquivo, categoria in arquivos:
                        if not arquivo:
                            continue
                        caminho = _salvar_upload_temporario(arquivo, diretorio)
                        resumo = comando.importar_arquivo(
                            caminho=caminho,
                            categoria=categoria,
                            somente_cadastro=False,
                        )
                        for chave, valor in resumo.items():
                            resumo_total[chave] += valor
            except CommandError as erro:
                messages.error(request, f"Nao foi possivel importar as planilhas: {erro}")
            else:
                messages.success(
                    request,
                    "Estoque ADM importado com sucesso: "
                    f"{resumo_total['itens_criados']} itens criados, "
                    f"{resumo_total['itens_atualizados']} atualizados, "
                    f"{resumo_total['entradas_criadas']} entradas, "
                    f"{resumo_total['saidas_criadas']} saidas.",
                )
                return redirect("estoque_adm")
    else:
        form = ImportarEstoquePlanilhasForm()

    context["form"] = form
    return render(request, "sistema/estoque_importar.html", context)


@login_required
def relatorio_estoque(request, modulo_codigo):
    modulo = _modulo_estoque_ou_404(modulo_codigo)
    area = area_do_modulo_estoque(modulo)
    titulo = f"Relatorio financeiro - {_titulo_estoque(modulo)}"
    context = contexto_modulo(
        request,
        modulo,
        titulo,
        "Analise custos, retiradas, entradas e comparativos por periodo.",
    )
    context["rota_estoque"] = rota_do_modulo_estoque(modulo)

    dados_formulario = _dados_relatorio_com_padrao(request.GET)
    form = RelatorioEstoqueFiltroForm(dados_formulario, modulo=modulo)
    movimentacoes = []
    relatorio = _montar_relatorio_estoque(movimentacoes)
    relatorio_valido = False
    estoque_atual = _montar_painel_estoque(area)
    itens_criticos = list(
        ItemEstoque.objects.filter(area=area).filter(
            Q(quantidade_atual__lte=0)
            | Q(estoque_minimo__gt=0, quantidade_atual__lt=F("estoque_minimo"))
        ).order_by("quantidade_atual", "nome")[:12]
    )

    if context["acesso_negado"]:
        context.update(
            {
                "form": form,
                "relatorio": relatorio,
                "totais": relatorio["totais"],
                "movimentacoes": movimentacoes,
                "estoque_atual": estoque_atual,
                "itens_criticos": itens_criticos,
                "relatorio_valido": relatorio_valido,
            }
        )
        return render(request, "sistema/estoque_relatorio.html", context)

    if form.is_valid():
        relatorio_valido = True
        filtros = form.cleaned_data
        movimentacoes = list(_movimentacoes_do_relatorio(area, filtros))
        itens_controle = _itens_controle_estoque(area, filtros)
        relatorio = _montar_relatorio_estoque(movimentacoes, itens_controle=itens_controle)

        if request.GET.get("export") == "csv":
            return _exportar_relatorio_csv(modulo, filtros, movimentacoes, relatorio)
        if request.GET.get("export") == "pdf":
            return _exportar_relatorio_pdf(modulo, filtros, movimentacoes, relatorio)

        context.update(
            {
                "data_inicio": filtros["data_inicio"],
                "data_fim": filtros["data_fim"],
                "periodo_label": (
                    _rotulo_mes(filtros["data_inicio"].year, filtros["data_inicio"].month)
                    if filtros.get("periodo") == "mes"
                    else "Periodo personalizado"
                ),
                "titulo_controle_estoque": _titulo_controle_estoque(modulo, filtros),
            }
        )

    context.update(
        {
            "form": form,
            "relatorio": relatorio,
            "totais": relatorio["totais"],
            "movimentacoes": movimentacoes,
            "estoque_atual": estoque_atual,
            "itens_criticos": itens_criticos,
            "relatorio_valido": relatorio_valido,
        }
    )
    return render(request, "sistema/estoque_relatorio.html", context)


@login_required
def categorias_estoque(request, modulo_codigo):
    modulo = _modulo_estoque_ou_404(modulo_codigo)
    area = area_do_modulo_estoque(modulo)
    context = contexto_modulo(
        request,
        modulo,
        f"Categorias - {_titulo_estoque(modulo)}",
        "Cadastre, edite e exclua categorias usadas nos itens deste estoque.",
    )
    if context["acesso_negado"]:
        return render(request, "sistema/categorias_estoque_lista.html", context)

    context.update(
        {
            "categorias": CategoriaEstoque.objects.filter(area=area).order_by("nome"),
            "rota_estoque": rota_do_modulo_estoque(modulo),
        }
    )
    return render(request, "sistema/categorias_estoque_lista.html", context)


@login_required
def nova_categoria_estoque(request, modulo_codigo):
    modulo = _modulo_estoque_ou_404(modulo_codigo)
    area = area_do_modulo_estoque(modulo)
    context = contexto_modulo(
        request,
        modulo,
        "Nova Categoria",
        f"Cadastre uma categoria para {_titulo_estoque(modulo)}.",
    )
    if context["acesso_negado"]:
        return render(
            request,
            "sistema/categoria_estoque_form.html",
            {**context, "form": CategoriaEstoqueForm(area=area)},
        )
    if not context["permite_edicao"]:
        messages.error(request, "Seu perfil permite apenas visualizar este estoque.")
        return redirect("categorias_estoque", modulo_codigo=modulo.value)

    if request.method == "POST":
        form = CategoriaEstoqueForm(request.POST, area=area)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria cadastrada com sucesso.")
            return redirect("categorias_estoque", modulo_codigo=modulo.value)
    else:
        form = CategoriaEstoqueForm(area=area)

    context["form"] = form
    return render(request, "sistema/categoria_estoque_form.html", context)


@login_required
def editar_categoria_estoque(request, pk):
    categoria, modulo = _categoria_estoque_com_modulo(pk)
    context = contexto_modulo(
        request,
        modulo,
        "Editar Categoria",
        f"Atualize a categoria {categoria.nome}.",
        extra={"categoria": categoria},
    )
    if context["acesso_negado"]:
        return render(
            request,
            "sistema/categoria_estoque_form.html",
            {**context, "form": CategoriaEstoqueForm(instance=categoria)},
        )
    if not context["permite_edicao"]:
        messages.error(request, "Seu perfil permite apenas visualizar este estoque.")
        return redirect("categorias_estoque", modulo_codigo=modulo.value)

    if request.method == "POST":
        form = CategoriaEstoqueForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria atualizada com sucesso.")
            return redirect("categorias_estoque", modulo_codigo=modulo.value)
    else:
        form = CategoriaEstoqueForm(instance=categoria)

    context["form"] = form
    return render(request, "sistema/categoria_estoque_form.html", context)


@login_required
def excluir_categoria_estoque(request, pk):
    categoria, modulo = _categoria_estoque_com_modulo(pk)
    context = contexto_modulo(
        request,
        modulo,
        "Excluir Categoria",
        f"Confirme a exclusao da categoria {categoria.nome}.",
        extra={"categoria": categoria},
    )
    if context["acesso_negado"]:
        return render(request, "sistema/categoria_estoque_confirmar_exclusao.html", context)
    if not context["permite_exclusao"]:
        messages.error(request, "Apenas administradores podem excluir categorias.")
        return redirect("categorias_estoque", modulo_codigo=modulo.value)

    itens_vinculados = ItemEstoque.objects.filter(
        area=categoria.area,
        categoria=categoria.codigo,
    ).count()
    context["itens_vinculados"] = itens_vinculados

    if request.method == "POST":
        if itens_vinculados:
            messages.error(
                request,
                "Esta categoria possui itens vinculados e nao pode ser excluida.",
            )
            return redirect("categorias_estoque", modulo_codigo=modulo.value)

        categoria.delete()
        messages.success(request, "Categoria excluida com sucesso.")
        return redirect("categorias_estoque", modulo_codigo=modulo.value)

    return render(request, "sistema/categoria_estoque_confirmar_exclusao.html", context)


@login_required
def novo_item_estoque(request, modulo_codigo):
    modulo = _modulo_estoque_ou_404(modulo_codigo)
    if not usuario_tem_acesso(request.user, modulo):
        return renderizar_modulo_sem_permissao(
            request,
            modulo,
            "Estoque",
            "Cadastro de itens de estoque.",
            "sistema/item_estoque_form.html",
            extra={"form": ItemEstoqueForm(modulo=modulo)},
        )
    if not usuario_pode_editar(request.user, modulo):
        messages.error(request, "Seu perfil permite apenas visualizar este estoque.")
        return redirect(rota_do_modulo_estoque(modulo))

    if request.method == "POST":
        form = ItemEstoqueForm(request.POST, modulo=modulo)
        if form.is_valid():
            item = form.save(commit=False)
            item.area = area_do_modulo_estoque(modulo)
            item.save()
            _ajustar_saldo_item(item, form.cleaned_data["saldo_atual"], request.user)
            messages.success(request, "Item de estoque cadastrado com sucesso.")
            return redirect(rota_do_modulo_estoque(modulo))
    else:
        form = ItemEstoqueForm(modulo=modulo)

    context = contexto_modulo(
        request,
        modulo,
        "Novo Item",
        "Cadastre um item no modulo de estoque.",
        extra={"form": form},
    )
    return render(request, "sistema/item_estoque_form.html", context)


@login_required
def editar_item_estoque(request, pk):
    item = get_object_or_404(ItemEstoque, pk=pk)
    modulo = _modulo_por_area_estoque(item.area)
    if not usuario_tem_acesso(request.user, modulo):
        return renderizar_modulo_sem_permissao(
            request,
            modulo,
            item.get_area_display(),
            "Edicao de item de estoque.",
            "sistema/item_estoque_form.html",
            extra={
                "item": item,
                "form": ItemEstoqueForm(
                    instance=item,
                    area=item.area,
                    exibir_categoria=False,
                ),
                "modo_edicao": True,
                "form_titulo": "Editar item",
                "form_descricao": "Atualize cadastro, valor e quantidade atual.",
            },
        )
    if not usuario_pode_editar(request.user, modulo):
        messages.error(request, "Seu perfil permite apenas visualizar este estoque.")
        return redirect("detalhe_item_estoque", pk=item.pk)

    if request.method == "POST":
        form = ItemEstoqueForm(
            request.POST,
            instance=item,
            area=item.area,
            exibir_categoria=False,
        )
        if form.is_valid():
            item = form.save(commit=False)
            item.area = area_do_modulo_estoque(modulo)
            item.save()
            ajustou_saldo = _ajustar_saldo_item(
                item,
                form.cleaned_data["saldo_atual"],
                request.user,
            )
            if ajustou_saldo:
                messages.success(request, "Item atualizado e saldo ajustado com sucesso.")
            else:
                messages.success(request, "Item atualizado com sucesso.")
            return redirect("detalhe_item_estoque", pk=item.pk)
    else:
        form = ItemEstoqueForm(instance=item, area=item.area, exibir_categoria=False)

    context = contexto_modulo(
        request,
        modulo,
        "Editar Item",
        "Atualize nome, valor e quantidade atual do produto.",
        extra={
            "item": item,
            "form": form,
            "modo_edicao": True,
            "form_titulo": "Editar item",
            "form_descricao": "Atualize cadastro, valor e quantidade atual.",
        },
    )
    return render(request, "sistema/item_estoque_form.html", context)


@login_required
def excluir_item_estoque(request, pk):
    item = get_object_or_404(ItemEstoque, pk=pk)
    modulo = _modulo_por_area_estoque(item.area)
    context = contexto_modulo(
        request,
        modulo,
        "Excluir Item",
        f"Confirme a exclusao do item {item.nome}.",
        extra={"item": item, "movimentacoes_vinculadas": item.movimentacoes.count()},
    )

    if context["acesso_negado"]:
        return render(request, "sistema/item_estoque_confirmar_exclusao.html", context)

    if not context["permite_exclusao"]:
        messages.error(request, "Apenas administradores podem excluir itens de estoque.")
        return redirect("detalhe_item_estoque", pk=item.pk)

    if request.method == "POST":
        rota_estoque = rota_do_modulo_estoque(modulo)
        item.delete()
        messages.success(request, "Item de estoque excluido com sucesso.")
        return redirect(rota_estoque)

    return render(request, "sistema/item_estoque_confirmar_exclusao.html", context)


@login_required
def detalhe_item_estoque(request, pk):
    item = get_object_or_404(ItemEstoque.objects.prefetch_related("movimentacoes"), pk=pk)
    modulo = _modulo_por_area_estoque(item.area)
    context = contexto_modulo(
        request,
        modulo,
        item.get_area_display(),
        "Acompanhe saldo, historico e movimente o estoque.",
        extra={"item": item, "movimentacoes": item.movimentacoes.select_related("responsavel")},
    )
    return render(request, "sistema/item_estoque_detalhe.html", context)


@login_required
def movimentar_item_estoque(request, pk):
    item = get_object_or_404(ItemEstoque, pk=pk)
    modulo = _modulo_por_area_estoque(item.area)
    if not usuario_tem_acesso(request.user, modulo):
        return renderizar_modulo_sem_permissao(
            request,
            modulo,
            item.get_area_display(),
            "Movimente o saldo do item.",
            "sistema/movimentacao_form.html",
            extra={"item": item, "form": MovimentacaoEstoqueForm()},
        )
    if not usuario_pode_editar(request.user, modulo):
        messages.error(request, "Seu perfil permite apenas visualizar este estoque.")
        return redirect("detalhe_item_estoque", pk=item.pk)

    if request.method == "POST":
        form = MovimentacaoEstoqueForm(request.POST)
        if form.is_valid():
            movimentacao = form.save(commit=False)
            movimentacao.item = item
            if not movimentacao.custo_unitario:
                movimentacao.custo_unitario = item.custo_unitario
            movimentacao.responsavel = request.user
            movimentacao.save()
            messages.success(request, "Movimentacao registrada e saldo atualizado automaticamente.")
            return redirect("detalhe_item_estoque", pk=item.pk)
    else:
        form = MovimentacaoEstoqueForm(
            initial={"custo_unitario": item.custo_unitario, "quantidade_devolvida": 0}
        )

    context = contexto_modulo(
        request,
        modulo,
        f"Movimentar {item.nome}",
        "Entradas e saidas recalculam o saldo total automaticamente.",
        extra={"item": item, "form": form},
    )
    return render(request, "sistema/movimentacao_form.html", context)
