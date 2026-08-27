import csv
from calendar import Calendar
from collections import defaultdict
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from sistema.models import ModuloSistema, Participante, Reuniao, ReuniaoLog
from sistema.permissions import usuario_eh_admin
from sistema.utils import enviar_email_reuniao, enviar_email_reuniao_finalizada

from ..common import MESES_PT_BR, contexto_modulo
from .forms import RelatorioReuniaoFiltroForm, ReuniaoForm
from .services import (
    agendar_whatsapp_reuniao_criada,
    atualizar_whatsapps_participantes,
    concluir_reunioes_expiradas,
    criar_log_reuniao,
    gerar_fingerprint_reuniao,
    identificadores_usuario,
    notificar_participantes_reuniao,
    obter_reunioes_do_usuario,
    usuario_pode_gerenciar_reuniao,
    vincular_novo_participante,
)


def montar_semanas_do_calendario(ano, mes, reunioes):
    reunioes_por_dia = defaultdict(list)

    for reuniao in reunioes:
        reunioes_por_dia[reuniao.data].append(reuniao)

    calendario = Calendar(firstweekday=6)
    hoje = date.today()

    return [
        [
            {
                "data": dia,
                "no_mes": dia.month == mes,
                "hoje": dia == hoje,
                "reunioes": reunioes_por_dia.get(dia, []),
            }
            for dia in semana
        ]
        for semana in calendario.monthdatescalendar(ano, mes)
    ]


def montar_resumo_agenda(reunioes):
    resumo = {
        "total": len(reunioes),
        "agendadas": 0,
        "realizadas": 0,
        "canceladas": 0,
        "dias_com_reuniao": 0,
        "salas": 0,
    }
    dias = set()
    salas = set()

    for reuniao in reunioes:
        dias.add(reuniao.data)
        if reuniao.sala_id:
            salas.add(reuniao.sala_id)
        if reuniao.status == Reuniao.Status.AGENDADA:
            resumo["agendadas"] += 1
        elif reuniao.status == Reuniao.Status.REALIZADA:
            resumo["realizadas"] += 1
        elif reuniao.status == Reuniao.Status.CANCELADA:
            resumo["canceladas"] += 1

    resumo["dias_com_reuniao"] = len(dias)
    resumo["salas"] = len(salas)
    return resumo


def agrupar_reunioes_por_data(reunioes):
    reunioes_por_data = defaultdict(list)
    for reuniao in reunioes:
        reunioes_por_data[reuniao.data].append(reuniao)

    return [
        {"data": data_reuniao, "reunioes": reunioes_por_data[data_reuniao]}
        for data_reuniao in sorted(reunioes_por_data)
    ]


def _dados_padrao_relatorio_reunioes():
    hoje = date.today()
    return {
        "data_inicio": date(hoje.year, hoje.month, 1).isoformat(),
        "data_fim": hoje.isoformat(),
    }


def _dados_relatorio_reunioes_com_padrao(query_params):
    dados = _dados_padrao_relatorio_reunioes()
    if query_params:
        dados.update(query_params.dict())
    return dados


def _queryset_relatorio_reunioes(usuario):
    if usuario_eh_admin(usuario, ModuloSistema.AGENDA):
        concluir_reunioes_expiradas()
        return Reuniao.objects.select_related("sala", "organizador_usuario").prefetch_related(
            "participantes"
        )
    return obter_reunioes_do_usuario(usuario, incluir_encerradas=True)


def _filtrar_reunioes_relatorio(queryset, filtros):
    reunioes = queryset.filter(
        data__gte=filtros["data_inicio"],
        data__lte=filtros["data_fim"],
    )

    if filtros.get("status"):
        reunioes = reunioes.filter(status=filtros["status"])

    pessoa = filtros.get("pessoa")
    if pessoa:
        reunioes = reunioes.filter(
            Q(organizador__icontains=pessoa)
            | Q(organizador_usuario__email__icontains=pessoa)
            | Q(organizador_usuario__first_name__icontains=pessoa)
            | Q(organizador_usuario__last_name__icontains=pessoa)
            | Q(participantes__nome__icontains=pessoa)
            | Q(participantes__email__icontains=pessoa)
        ).distinct()

    return reunioes.order_by("data", "hora_inicio", "sala__nome")


def _resumo_relatorio_reunioes(reunioes):
    resumo = {
        "total": len(reunioes),
        "agendadas": 0,
        "realizadas": 0,
        "canceladas": 0,
    }
    for reuniao in reunioes:
        if reuniao.status == Reuniao.Status.AGENDADA:
            resumo["agendadas"] += 1
        elif reuniao.status == Reuniao.Status.REALIZADA:
            resumo["realizadas"] += 1
        elif reuniao.status == Reuniao.Status.CANCELADA:
            resumo["canceladas"] += 1
    return resumo


def _exportar_relatorio_reunioes_csv(filtros, reunioes):
    nome_arquivo = f"relatorio_reunioes_{filtros['data_inicio']}_{filtros['data_fim']}.csv"
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    resposta.write("\ufeff")

    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow(["Relatorio de reunioes"])
    escritor.writerow(["Periodo", filtros["data_inicio"].strftime("%d/%m/%Y"), filtros["data_fim"].strftime("%d/%m/%Y")])
    escritor.writerow(["Status", Reuniao.Status(filtros["status"]).label if filtros.get("status") else "Todos"])
    escritor.writerow(["Pessoa/e-mail", filtros.get("pessoa") or "Todos"])
    escritor.writerow([])
    escritor.writerow(["Data", "Horario", "Titulo", "Sala", "Status", "Organizador", "Participantes"])

    for reuniao in reunioes:
        participantes = "; ".join(
            f"{participante.nome} ({participante.email or 'sem e-mail'})"
            for participante in reuniao.participantes.all()
        )
        escritor.writerow(
            [
                reuniao.data.strftime("%d/%m/%Y"),
                f"{reuniao.hora_inicio.strftime('%H:%M')} - {reuniao.hora_fim.strftime('%H:%M')}",
                reuniao.titulo,
                reuniao.sala.nome,
                reuniao.get_status_display(),
                reuniao.nome_organizador,
                participantes,
            ]
        )

    return resposta


def mes_anterior_proximo(ano, mes):
    if mes == 1:
        mes_anterior = {"ano": ano - 1, "mes": 12}
    else:
        mes_anterior = {"ano": ano, "mes": mes - 1}

    if mes == 12:
        proximo_mes = {"ano": ano + 1, "mes": 1}
    else:
        proximo_mes = {"ano": ano, "mes": mes + 1}

    return mes_anterior, proximo_mes


def participantes_selecionados_para_form(form):
    if form.is_bound:
        participantes_ids = form.data.getlist("participantes")
        participantes = Participante.objects.filter(pk__in=participantes_ids).order_by("nome")
    elif form.instance and form.instance.pk:
        participantes = form.instance.participantes.all().order_by("nome")
    else:
        participantes = Participante.objects.none()

    resultado = []
    for participante in participantes:
        nome_campo = form.nome_campo_whatsapp_participante(participante.pk)
        whatsapp = (
            form.data.get(nome_campo, participante.whatsapp or "")
            if form.is_bound
            else participante.whatsapp or ""
        )
        resultado.append(
            {
                "id": participante.pk,
                "nome": participante.nome,
                "email": participante.email or "",
                "whatsapp": whatsapp,
            }
        )
    return resultado


@login_required
def home(request):
    context = contexto_modulo(
        request,
        ModuloSistema.AGENDA,
        "Minha Agenda",
        "Reunioes integradas com participantes, notificacoes e controle por perfil.",
    )
    if context["acesso_negado"]:
        return render(request, "sistema/home.html", context)

    if usuario_eh_admin(request.user, ModuloSistema.AGENDA):
        concluir_reunioes_expiradas()
        reunioes = Reuniao.objects.select_related(
            "sala",
            "organizador_usuario",
        ).prefetch_related("participantes").order_by("data", "hora_inicio")
    else:
        reunioes = obter_reunioes_do_usuario(request.user, incluir_encerradas=True)
    reunioes_por_ano_mes = defaultdict(list)

    for reuniao in reunioes:
        reunioes_por_ano_mes[reuniao.data.year].append(
            {"numero": reuniao.data.month, "nome": MESES_PT_BR[reuniao.data.month]}
        )

    agenda_organizada = []
    for ano, meses in reunioes_por_ano_mes.items():
        vistos = set()
        meses_unicos = []
        for mes in sorted(meses, key=lambda item: item["numero"]):
            if mes["numero"] not in vistos:
                meses_unicos.append(mes)
                vistos.add(mes["numero"])
        agenda_organizada.append({"ano": ano, "meses": meses_unicos})

    context.update(
        {
            "agenda_organizada": sorted(
                agenda_organizada, key=lambda item: item["ano"], reverse=True
            ),
            "hoje": date.today(),
            "total_reunioes": reunioes.count(),
            "proximas_reunioes": reunioes.filter(
                data__gte=date.today(), status=Reuniao.Status.AGENDADA
            ).count(),
        }
    )
    return render(request, "sistema/home.html", context)


@login_required
def lista_reunioes_mes(request, ano, mes):
    context = contexto_modulo(
        request,
        ModuloSistema.AGENDA,
        "Minha Agenda",
        "Visualize as reunioes do periodo selecionado.",
    )
    if context["acesso_negado"]:
        if mes < 1 or mes > 12:
            messages.error(request, "Mes invalido.")
            return redirect("home")
        mes_anterior, proximo_mes = mes_anterior_proximo(ano, mes)
        context.update(
            {
                "ano": ano,
                "mes": mes,
                "mes_nome": MESES_PT_BR.get(mes, str(mes)),
                "mes_anterior": mes_anterior,
                "proximo_mes": proximo_mes,
                "query_filtros": "",
            }
        )
        return render(request, "sistema/agenda_mes.html", context)

    if mes < 1 or mes > 12:
        messages.error(request, "Mes invalido.")
        return redirect("home")

    if usuario_eh_admin(request.user, ModuloSistema.AGENDA):
        concluir_reunioes_expiradas()
        reunioes = Reuniao.objects.select_related("sala", "organizador_usuario").prefetch_related(
            "participantes"
        )
    else:
        reunioes = obter_reunioes_do_usuario(request.user, incluir_encerradas=True)

    reunioes = reunioes.filter(data__year=ano, data__month=mes)
    status_filtro = request.GET.get("status", "").strip()
    email_filtro = request.GET.get("email", "").strip()
    status_validos = {status for status, _ in Reuniao.Status.choices}
    if status_filtro and status_filtro in status_validos:
        reunioes = reunioes.filter(status=status_filtro)
    else:
        status_filtro = ""

    if email_filtro:
        reunioes = reunioes.filter(
            Q(organizador__iexact=email_filtro)
            | Q(organizador_usuario__email__iexact=email_filtro)
            | Q(participantes__email__iexact=email_filtro)
        ).distinct()
        if not status_filtro:
            reunioes = reunioes.exclude(status=Reuniao.Status.CANCELADA)

    reunioes = list(reunioes.order_by("data", "hora_inicio"))
    dia_selecionado = None
    dia_parametro = request.GET.get("dia", "").strip()
    if dia_parametro:
        try:
            dia_candidato = date.fromisoformat(dia_parametro)
        except ValueError:
            dia_parametro = ""
        else:
            if dia_candidato.year == ano and dia_candidato.month == mes:
                dia_selecionado = dia_candidato
            else:
                dia_parametro = ""

    reunioes_dia = [
        reuniao for reuniao in reunioes if reuniao.data == dia_selecionado
    ]
    mes_anterior, proximo_mes = mes_anterior_proximo(ano, mes)
    query_filtros = urlencode(
        {
            chave: valor
            for chave, valor in {
                "status": status_filtro,
                "email": email_filtro,
            }.items()
            if valor
        }
    )

    context.update(
        {
            "reunioes": reunioes,
            "semanas": montar_semanas_do_calendario(ano, mes, reunioes),
            "resumo_agenda": montar_resumo_agenda(reunioes),
            "reunioes_por_data": agrupar_reunioes_por_data(reunioes),
            "dia_selecionado": dia_selecionado,
            "dia_parametro": dia_parametro,
            "reunioes_dia": reunioes_dia,
            "ano": ano,
            "mes": mes,
            "mes_nome": MESES_PT_BR.get(mes, str(mes)),
            "status_filtro": status_filtro,
            "email_filtro": email_filtro,
            "status_opcoes": Reuniao.Status.choices,
            "mes_anterior": mes_anterior,
            "proximo_mes": proximo_mes,
            "query_filtros": query_filtros,
            "usuario_pode_gerenciar_tudo": usuario_eh_admin(request.user, ModuloSistema.AGENDA),
            "identificadores_usuario": identificadores_usuario(request.user),
        }
    )
    return render(request, "sistema/agenda_mes.html", context)


@login_required
def detalhe_reuniao(request, pk):
    context = contexto_modulo(
        request,
        ModuloSistema.AGENDA,
        "Minha Agenda",
        "Detalhes completos da reuniao.",
    )
    reuniao = get_object_or_404(
        Reuniao.objects.select_related("sala", "organizador_usuario").prefetch_related("participantes"),
        pk=pk,
    )
    if context["acesso_negado"]:
        return render(request, "sistema/detalhe_reuniao.html", {**context, "reuniao": reuniao})

    usuario_pode_ver = usuario_eh_admin(
        request.user, ModuloSistema.AGENDA
    ) or usuario_pode_gerenciar_reuniao(request.user, reuniao)
    if request.user.email and reuniao.participantes.filter(email__iexact=request.user.email).exists():
        usuario_pode_ver = True

    if not usuario_pode_ver:
        messages.error(request, "Voce nao tem permissao para visualizar esta reuniao.")
        return redirect("home")

    context.update(
        {
            "reuniao": reuniao,
            "emails_participantes": reuniao.participantes.all().order_by("nome"),
            "usuario_pode_gerenciar": usuario_pode_gerenciar_reuniao(request.user, reuniao),
        }
    )
    return render(request, "sistema/detalhe_reuniao.html", context)


@login_required
def nova_reuniao(request):
    context = contexto_modulo(
        request,
        ModuloSistema.AGENDA,
        "Minha Agenda",
        "Crie uma reuniao e notifique automaticamente os participantes.",
    )
    if context["acesso_negado"]:
        form = ReuniaoForm()
        return render(
            request,
            "sistema/nova_reuniao.html",
            {
                **context,
                "form": form,
                "participantes_selecionados": participantes_selecionados_para_form(form),
            },
        )
    if not context["permite_edicao"]:
        messages.error(request, "Seu perfil permite apenas visualizar a agenda de reunioes.")
        return redirect("home")

    if request.method == "POST":
        fingerprint = gerar_fingerprint_reuniao(request.POST, request.user)
        if request.session.get("ultima_reuniao_criada_fingerprint") == fingerprint:
            messages.info(request, "Essa reuniao ja foi criada. Evitamos um envio duplicado.")
            return redirect("home")

        form = ReuniaoForm(request.POST)
        if form.is_valid():
            resultado_whatsapp = {}
            with transaction.atomic():
                reuniao = form.save(commit=False)
                reuniao.organizador_usuario = request.user
                reuniao.organizador = (
                    request.user.get_full_name() or request.user.email or request.user.username
                )
                reuniao.save()
                form.save_m2m()
                atualizar_whatsapps_participantes(form, reuniao)
                vincular_novo_participante(form, reuniao)
                criar_log_reuniao(
                    reuniao,
                    request.user,
                    ReuniaoLog.Acao.CRIACAO,
                    "Reuniao criada.",
                )
                notificar_participantes_reuniao(reuniao, "criacao", request.user)
                agendar_whatsapp_reuniao_criada(reuniao, resultado_whatsapp)

            erros_avisos = []
            try:
                enviar_email_reuniao(reuniao, tipo="criacao")
            except Exception as erro:
                erros_avisos.append(f"e-mail aos participantes: {erro}")

            if resultado_whatsapp.get("falhas"):
                primeiro_erro = (resultado_whatsapp.get("erros") or [{}])[0]
                status_http = primeiro_erro.get("status_http")
                detalhe = primeiro_erro.get("mensagem") or "falha nao informada pela Meta"
                if status_http:
                    detalhe = f"HTTP {status_http}: {detalhe}"
                erros_avisos.append(f"WhatsApp: {detalhe}")

            if erros_avisos:
                messages.warning(
                    request,
                    "Reuniao criada, mas houve falha no envio de "
                    + "; ".join(erros_avisos)
                    + ".",
                )
            else:
                messages.success(request, "Reuniao criada com sucesso e notificacoes enviadas.")

            request.session["ultima_reuniao_criada_fingerprint"] = fingerprint
            return redirect("detalhe_reuniao", pk=reuniao.pk)
    else:
        form = ReuniaoForm()
        request.session.pop("ultima_reuniao_criada_fingerprint", None)

    return render(
        request,
        "sistema/nova_reuniao.html",
        {
            **context,
            "form": form,
            "participantes_selecionados": participantes_selecionados_para_form(form),
        },
    )


@login_required
def editar_reuniao(request, pk):
    reuniao = get_object_or_404(Reuniao, pk=pk)
    context = contexto_modulo(
        request,
        ModuloSistema.AGENDA,
        "Minha Agenda",
        "Edicao de reunioes existentes.",
        extra={"reuniao": reuniao},
    )
    if context["acesso_negado"]:
        form = ReuniaoForm(instance=reuniao)
        return render(
            request,
            "sistema/editar_reuniao.html",
            {
                **context,
                "form": form,
                "participantes_selecionados": participantes_selecionados_para_form(form),
            },
        )
    if not usuario_pode_gerenciar_reuniao(request.user, reuniao):
        messages.error(request, "Voce nao tem permissao para editar esta reuniao.")
        return redirect("home")

    if request.method == "POST":
        status_anterior = reuniao.status
        form = ReuniaoForm(request.POST, instance=reuniao)
        if form.is_valid():
            reuniao = form.save(commit=False)
            reuniao.organizador_usuario = reuniao.organizador_usuario or request.user
            reuniao.organizador = (
                reuniao.organizador_usuario.get_full_name()
                or reuniao.organizador_usuario.email
                or reuniao.organizador
            )
            reuniao.save()
            form.save_m2m()
            atualizar_whatsapps_participantes(form, reuniao)
            vincular_novo_participante(form, reuniao)
            criar_log_reuniao(reuniao, request.user, ReuniaoLog.Acao.EDICAO, "Reuniao editada.")
            notificar_participantes_reuniao(reuniao, "edicao", request.user)

            erros_avisos = []
            try:
                enviar_email_reuniao(reuniao, tipo="edicao")
            except Exception as erro:
                erros_avisos.append(f"e-mail aos participantes: {erro}")

            if status_anterior != Reuniao.Status.REALIZADA and reuniao.status == Reuniao.Status.REALIZADA:
                try:
                    email_enviado = enviar_email_reuniao_finalizada(reuniao)
                    if not email_enviado:
                        erros_avisos.append("criador sem e-mail cadastrado")
                except Exception as erro:
                    erros_avisos.append(f"e-mail ao criador: {erro}")

            if erros_avisos:
                messages.warning(
                    request,
                    "Reuniao atualizada, mas houve falha no envio de "
                    + "; ".join(erros_avisos)
                    + ".",
                )
            else:
                messages.success(request, "Reuniao atualizada com sucesso e notificacoes enviadas.")

            return redirect("detalhe_reuniao", pk=reuniao.pk)
    else:
        form = ReuniaoForm(instance=reuniao)

    return render(
        request,
        "sistema/editar_reuniao.html",
        {
            **context,
            "form": form,
            "participantes_selecionados": participantes_selecionados_para_form(form),
        },
    )


@login_required
def cancelar_reuniao(request, pk):
    reuniao = get_object_or_404(Reuniao, pk=pk)
    if not usuario_pode_gerenciar_reuniao(request.user, reuniao):
        messages.error(request, "Voce nao tem permissao para cancelar esta reuniao.")
        return redirect("home")

    if request.method == "POST":
        reuniao.status = Reuniao.Status.CANCELADA
        reuniao.save(update_fields=["status", "atualizada_em"])
        criar_log_reuniao(reuniao, request.user, ReuniaoLog.Acao.CANCELAMENTO, "Reuniao cancelada.")
        notificar_participantes_reuniao(reuniao, "cancelamento", request.user)

        erros_avisos = []
        try:
            enviar_email_reuniao(reuniao, tipo="cancelamento")
        except Exception as erro:
            erros_avisos.append(f"e-mail: {erro}")

        if erros_avisos:
            messages.warning(
                request,
                "Reuniao cancelada, mas houve falha no envio de "
                + "; ".join(erros_avisos)
                + ".",
            )
        else:
            messages.success(request, "Reuniao cancelada com sucesso e participantes avisados.")

        return redirect("detalhe_reuniao", pk=reuniao.pk)

    context = contexto_modulo(
        request,
        ModuloSistema.AGENDA,
        "Minha Agenda",
        "Cancelamento de reunioes.",
        extra={"reuniao": reuniao},
    )
    return render(request, "sistema/cancelar_reuniao.html", context)


@login_required
def reenviar_email_reuniao(request, pk):
    reuniao = get_object_or_404(Reuniao, pk=pk)
    if not usuario_pode_gerenciar_reuniao(request.user, reuniao):
        messages.error(request, "Voce nao tem permissao para reenviar este aviso.")
        return redirect("home")

    erros_avisos = []
    try:
        enviar_email_reuniao(reuniao, tipo="edicao")
    except Exception as erro:
        erros_avisos.append(f"e-mail: {erro}")

    if erros_avisos:
        messages.error(request, "Erro ao reenviar aviso: " + "; ".join(erros_avisos) + ".")
    else:
        messages.success(request, "Aviso reenviado com sucesso.")
    return redirect("detalhe_reuniao", pk=pk)


@login_required
def buscar_participantes(request):
    termo = request.GET.get("q", "").strip()
    participantes = Participante.objects.all().order_by("nome")
    if termo:
        participantes = participantes.filter(Q(nome__icontains=termo) | Q(email__icontains=termo))
    resultados = [
        {
            "id": participante.id,
            "nome": participante.nome,
            "email": participante.email or "",
            "whatsapp": participante.whatsapp or "",
        }
        for participante in participantes[:12]
    ]
    return JsonResponse({"resultados": resultados})


@login_required
def relatorio_reunioes(request):
    context = contexto_modulo(
        request,
        ModuloSistema.AGENDA,
        "Relatorio de Reunioes",
        "Filtre reunioes por pessoa, e-mail, status e periodo.",
    )
    dados_formulario = _dados_relatorio_reunioes_com_padrao(request.GET)
    form = RelatorioReuniaoFiltroForm(dados_formulario)
    reunioes = []
    resumo = _resumo_relatorio_reunioes(reunioes)
    relatorio_valido = False

    if not context["acesso_negado"] and form.is_valid():
        relatorio_valido = True
        filtros = form.cleaned_data
        reunioes = list(_filtrar_reunioes_relatorio(_queryset_relatorio_reunioes(request.user), filtros))
        resumo = _resumo_relatorio_reunioes(reunioes)

        if request.GET.get("export") == "csv":
            return _exportar_relatorio_reunioes_csv(filtros, reunioes)

        context.update(
            {
                "data_inicio": filtros["data_inicio"],
                "data_fim": filtros["data_fim"],
            }
        )

    context.update(
        {
            "form": form,
            "reunioes": reunioes,
            "resumo": resumo,
            "relatorio_valido": relatorio_valido,
        }
    )
    return render(request, "sistema/relatorio_reunioes.html", context)
