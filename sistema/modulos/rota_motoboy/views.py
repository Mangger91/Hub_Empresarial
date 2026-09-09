from collections import defaultdict
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Q
from django.forms import formset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from sistema.models import EnderecoEmpresaMotoboy, ModuloSistema, RotaMotoboy, RotaParada

from ..common import MESES_PT_BR, contexto_modulo
from .forms import EnderecoEmpresaMotoboyForm, RotaMotoboyForm, RotaParadaCriacaoForm
from .roteirizacao import RoteirizacaoError, buscar_sugestoes_endereco, otimizar_rota_motoboy


RotaParadaCriacaoFormSet = formset_factory(
    RotaParadaCriacaoForm,
    extra=0,
    min_num=1,
    validate_min=True,
)


def _salvar_paradas_da_rota(rota, formset):
    ordem = 1
    for parada_form in formset:
        if not parada_form.cleaned_data:
            continue
        parada = parada_form.save(commit=False)
        parada.rota = rota
        parada.ordem = ordem
        parada.save()
        _sincronizar_endereco_empresa(parada)
        ordem += 1


def _preparar_rota_sem_destino_final(rota):
    rota.titulo = ""
    rota.endereco_destino = ""
    rota.latitude_destino = None
    rota.longitude_destino = None


def _sincronizar_endereco_empresa(parada):
    nome = (parada.empresa or "").strip()
    endereco = (parada.endereco or "").strip()
    if not nome or not endereco:
        return

    endereco_empresa = EnderecoEmpresaMotoboy.objects.filter(nome__iexact=nome).first()
    if endereco_empresa:
        if endereco_empresa.endereco != endereco:
            endereco_empresa.endereco = endereco
            endereco_empresa.ativo = True
            endereco_empresa.save(update_fields=["endereco", "ativo", "atualizado_em"])
        return

    EnderecoEmpresaMotoboy.objects.create(nome=nome, endereco=endereco)


@login_required
def rota_motoboy(request):
    context = contexto_modulo(
        request,
        ModuloSistema.ROTA_MOTOBOY,
        "Rota do MotoBoy",
        "Acompanhe as rotas por ano, mes e paradas de coleta/entrega.",
    )
    if context["acesso_negado"]:
        return render(request, "sistema/rota_motoboy.html", context)

    rotas = RotaMotoboy.objects.all()
    mapa = defaultdict(set)
    for rota in rotas:
        mapa[rota.data.year].add(rota.data.month)

    agenda_organizada = []
    for ano, meses in sorted(mapa.items(), key=lambda item: item[0], reverse=True):
        agenda_organizada.append(
            {
                "ano": ano,
                "meses": [
                    {"numero": mes, "nome": MESES_PT_BR.get(mes, str(mes))}
                    for mes in sorted(meses)
                ],
            }
        )

    context["agenda_organizada"] = agenda_organizada
    return render(request, "sistema/rota_motoboy.html", context)


@login_required
def enderecos_empresas_rota(request):
    context = contexto_modulo(
        request,
        ModuloSistema.ROTA_MOTOBOY,
        "Enderecos de Empresas",
        "Cadastre empresas e enderecos usados nas rotas do motoboy.",
    )
    if context["acesso_negado"]:
        return render(
            request,
            "sistema/enderecos_empresas_rota.html",
            {**context, "form": EnderecoEmpresaMotoboyForm(), "enderecos": []},
        )
    if request.method == "POST":
        if not context["permite_edicao"]:
            messages.error(request, "Seu perfil permite apenas visualizar este modulo.")
            return redirect("enderecos_empresas_rota")

        form = EnderecoEmpresaMotoboyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Endereco de empresa cadastrado com sucesso.")
            return redirect("enderecos_empresas_rota")
    else:
        form = EnderecoEmpresaMotoboyForm()

    context.update(
        {
            "form": form,
            "enderecos": EnderecoEmpresaMotoboy.objects.all(),
        }
    )
    return render(request, "sistema/enderecos_empresas_rota.html", context)


@login_required
def editar_endereco_empresa_rota(request, pk):
    endereco = get_object_or_404(EnderecoEmpresaMotoboy, pk=pk)
    context = contexto_modulo(
        request,
        ModuloSistema.ROTA_MOTOBOY,
        "Editar Endereco",
        "Atualize o cadastro de empresa usado nas rotas.",
        extra={"endereco": endereco},
    )
    if context["acesso_negado"]:
        return render(
            request,
            "sistema/endereco_empresa_rota_form.html",
            {**context, "form": EnderecoEmpresaMotoboyForm(instance=endereco)},
        )
    if not context["permite_edicao"]:
        messages.error(request, "Seu perfil permite apenas visualizar este modulo.")
        return redirect("enderecos_empresas_rota")

    if request.method == "POST":
        form = EnderecoEmpresaMotoboyForm(request.POST, instance=endereco)
        if form.is_valid():
            form.save()
            messages.success(request, "Endereco atualizado com sucesso.")
            return redirect("enderecos_empresas_rota")
    else:
        form = EnderecoEmpresaMotoboyForm(instance=endereco)

    context["form"] = form
    return render(request, "sistema/endereco_empresa_rota_form.html", context)


@login_required
def rota_motoboy_mes(request, ano, mes):
    context = contexto_modulo(
        request,
        ModuloSistema.ROTA_MOTOBOY,
        "Rota do MotoBoy",
        "Rotas cadastradas no periodo selecionado.",
    )
    if context["acesso_negado"]:
        return render(request, "sistema/rota_motoboy_mes.html", context)

    rotas_queryset = RotaMotoboy.objects.prefetch_related("paradas").filter(
        data__year=ano,
        data__month=mes,
    ).order_by("data", "id")
    total_rotas_abertas = rotas_queryset.filter(status=RotaMotoboy.Status.ABERTA).count()
    km_total_mes = sum(
        (
            rota.distancia_total_km
            for rota in rotas_queryset.filter(status=RotaMotoboy.Status.CONCLUIDA)
        ),
        0,
    )
    rotas = list(rotas_queryset)
    rotas_agrupadas = defaultdict(list)
    for rota in rotas:
        rotas_agrupadas[rota.data].append(rota)

    context.update(
        {
            "rotas": rotas,
            "rotas_por_data": [
                {"data": data_rota, "rotas": rotas_do_dia}
                for data_rota, rotas_do_dia in rotas_agrupadas.items()
            ],
            "total_rotas_abertas": total_rotas_abertas,
            "km_total_mes": km_total_mes,
            "ano": ano,
            "mes": mes,
            "mes_nome": MESES_PT_BR.get(mes, str(mes)),
        }
    )
    return render(request, "sistema/rota_motoboy_mes.html", context)


@login_required
def rota_motoboy_nova(request):
    context = contexto_modulo(
        request,
        ModuloSistema.ROTA_MOTOBOY,
        "Nova Rota",
        "Monte a rota completa, adicione as paradas e salve para calcular a melhor sequencia.",
    )
    if context["acesso_negado"]:
        return render(
            request,
            "sistema/rota_motoboy_form.html",
            {
                **context,
                "form": RotaMotoboyForm(),
                "paradas_formset": RotaParadaCriacaoFormSet(prefix="paradas"),
            },
        )
    if not context["permite_edicao"]:
        messages.error(request, "Seu perfil permite apenas visualizar este modulo.")
        return redirect("rota_motoboy")

    if request.method == "POST":
        form = RotaMotoboyForm(request.POST)
        paradas_formset = RotaParadaCriacaoFormSet(request.POST, prefix="paradas")
        if form.is_valid() and paradas_formset.is_valid():
            rota = form.save(commit=False)
            _preparar_rota_sem_destino_final(rota)
            rota.responsavel = request.user
            rota.save()
            _salvar_paradas_da_rota(rota, paradas_formset)
            try:
                otimizar_rota_motoboy(rota)
            except RoteirizacaoError as erro:
                messages.warning(
                    request,
                    f"Rota salva, mas nao foi possivel calcular a quilometragem: {erro}",
                )
            else:
                messages.success(request, "Rota criada, otimizada e quilometragem calculada.")
            return redirect("rota_motoboy_detalhe", pk=rota.pk)
    else:
        form = RotaMotoboyForm(initial={"data": date.today()})
        paradas_formset = RotaParadaCriacaoFormSet(prefix="paradas")

    return render(
        request,
        "sistema/rota_motoboy_form.html",
        {
            **context,
            "form": form,
            "paradas_formset": paradas_formset,
            "criacao": True,
            "buscar_endereco_url": "buscar_enderecos_rota",
        },
    )


@login_required
def rota_motoboy_editar(request, pk):
    rota = get_object_or_404(RotaMotoboy.objects.prefetch_related("paradas"), pk=pk)
    context = contexto_modulo(
        request,
        ModuloSistema.ROTA_MOTOBOY,
        "Editar Rota",
        "Atualize os dados da rota e suas paradas antes de salvar.",
    )
    if context["acesso_negado"]:
        return render(
            request,
            "sistema/rota_motoboy_form.html",
            {
                **context,
                "form": RotaMotoboyForm(instance=rota),
                "paradas_formset": RotaParadaCriacaoFormSet(prefix="paradas"),
            },
        )
    if not context["permite_edicao"]:
        messages.error(request, "Seu perfil permite apenas visualizar este modulo.")
        return redirect("rota_motoboy_detalhe", pk=rota.pk)

    if request.method == "POST":
        form = RotaMotoboyForm(request.POST, instance=rota)
        paradas_formset = RotaParadaCriacaoFormSet(request.POST, prefix="paradas")
        if form.is_valid() and paradas_formset.is_valid():
            rota = form.save(commit=False)
            _preparar_rota_sem_destino_final(rota)
            rota.atualizado_em = timezone.now()
            rota.save()
            rota.paradas.all().delete()
            _salvar_paradas_da_rota(rota, paradas_formset)
            try:
                otimizar_rota_motoboy(rota)
            except RoteirizacaoError as erro:
                messages.warning(
                    request,
                    f"Rota atualizada, mas nao foi possivel recalcular a quilometragem: {erro}",
                )
            else:
                messages.success(request, "Rota atualizada e recalculada com sucesso.")
            return redirect("rota_motoboy_detalhe", pk=rota.pk)
    else:
        form = RotaMotoboyForm(instance=rota)
        paradas_formset = RotaParadaCriacaoFormSet(prefix="paradas")

    return render(
        request,
        "sistema/rota_motoboy_form.html",
        {
            **context,
            "form": form,
            "paradas_formset": paradas_formset,
            "criacao": False,
            "buscar_endereco_url": "buscar_enderecos_rota",
        },
    )


@login_required
def rota_motoboy_detalhe(request, pk):
    rota = get_object_or_404(RotaMotoboy.objects.prefetch_related("paradas"), pk=pk)
    parada_form = RotaParadaCriacaoForm()
    context = contexto_modulo(
        request,
        ModuloSistema.ROTA_MOTOBOY,
        "Detalhes da Rota",
        "Gerencie as paradas planejadas para a rota.",
        extra={"rota": rota},
    )
    if context["acesso_negado"]:
        return render(
            request,
            "sistema/rota_motoboy_detalhe.html",
            context,
        )

    if request.method == "POST":
        if not context["permite_edicao"]:
            messages.error(request, "Seu perfil permite apenas visualizar este modulo.")
            return redirect("rota_motoboy_detalhe", pk=rota.pk)

        acao_rota = request.POST.get("acao_rota")
        if acao_rota == "adicionar_parada":
            parada_form = RotaParadaCriacaoForm(request.POST)
            if parada_form.is_valid():
                parada = parada_form.save(commit=False)
                parada.rota = rota
                ultima_ordem = rota.paradas.aggregate(maior=Max("ordem"))["maior"] or 0
                parada.ordem = ultima_ordem + 1
                parada.save()
                _sincronizar_endereco_empresa(parada)
                try:
                    otimizar_rota_motoboy(rota)
                except RoteirizacaoError as erro:
                    rota.distancia_total_km = 0
                    rota.duracao_total_minutos = 0
                    rota.rota_otimizada_em = None
                    rota.save(
                        update_fields=[
                            "distancia_total_km",
                            "duracao_total_minutos",
                            "rota_otimizada_em",
                            "atualizado_em",
                        ]
                    )
                    messages.warning(
                        request,
                        f"Parada adicionada, mas nao foi possivel recalcular a rota: {erro}",
                    )
                else:
                    messages.success(request, "Parada adicionada e rota recalculada.")
                return redirect("rota_motoboy_detalhe", pk=rota.pk)

        if acao_rota == "otimizar":
            try:
                otimizar_rota_motoboy(rota)
            except RoteirizacaoError as erro:
                messages.error(request, str(erro))
            else:
                messages.success(request, "Rota otimizada e quilometragem calculada.")
            return redirect("rota_motoboy_detalhe", pk=rota.pk)

        if acao_rota in {"concluir", "cancelar"}:
            rota.status = (
                RotaMotoboy.Status.CONCLUIDA
                if acao_rota == "concluir"
                else RotaMotoboy.Status.CANCELADA
            )
            rota.save(update_fields=["status", "atualizado_em"])
            messages.success(request, "Status da rota atualizado com sucesso.")
            return redirect("rota_motoboy_mes", ano=rota.data.year, mes=rota.data.month)

    context["parada_form"] = parada_form
    return render(request, "sistema/rota_motoboy_detalhe.html", context)


@login_required
def buscar_enderecos_rota(request):
    termo = request.GET.get("q", "").strip()
    resultados = []
    enderecos_vistos = set()

    def adicionar_resultado(nome, empresa="", origem="salvo"):
        nome = " ".join(str(nome or "").split())
        empresa = " ".join(str(empresa or "").split())
        chave = nome.casefold()
        if not nome or chave in enderecos_vistos:
            return
        resultados.append({"nome": nome, "empresa": empresa, "origem": origem})
        enderecos_vistos.add(chave)

    enderecos_salvos = EnderecoEmpresaMotoboy.objects.filter(ativo=True)
    if termo:
        enderecos_salvos = enderecos_salvos.filter(
            Q(nome__icontains=termo) | Q(endereco__icontains=termo)
        )

    for endereco in enderecos_salvos[:10]:
        adicionar_resultado(endereco.endereco, endereco.nome)

    paradas = RotaParada.objects.exclude(endereco="")
    if termo:
        paradas = paradas.filter(Q(empresa__icontains=termo) | Q(endereco__icontains=termo))
    for parada in paradas.order_by("-criado_em")[:12]:
        adicionar_resultado(parada.endereco, parada.empresa, "historico")

    if len(termo) < 3:
        return JsonResponse({"resultados": resultados})

    try:
        sugestoes_mapa = buscar_sugestoes_endereco(termo)
    except RoteirizacaoError:
        sugestoes_mapa = []

    for sugestao in sugestoes_mapa:
        adicionar_resultado(sugestao.get("nome"), origem="mapa")
    return JsonResponse({"resultados": resultados})


@login_required
def buscar_empresas_rota(request):
    termo = request.GET.get("q", "").strip()
    resultados = []
    empresas_vistas = set()

    def adicionar_empresa(nome, endereco):
        nome = " ".join(str(nome or "").split())
        endereco = " ".join(str(endereco or "").split())
        chave = nome.casefold()
        if not nome or not endereco or chave in empresas_vistas:
            return None
        resultados.append({"id": None, "nome": nome, "endereco": endereco})
        empresas_vistas.add(chave)
        return resultados[-1]

    enderecos = EnderecoEmpresaMotoboy.objects.filter(ativo=True)
    if termo:
        enderecos = enderecos.filter(Q(nome__icontains=termo) | Q(endereco__icontains=termo))

    for endereco in enderecos[:12]:
        resultado = adicionar_empresa(endereco.nome, endereco.endereco)
        if resultado:
            resultado["id"] = endereco.pk

    if len(resultados) < 12:
        paradas = RotaParada.objects.exclude(empresa="").exclude(endereco="")
        if termo:
            paradas = paradas.filter(Q(empresa__icontains=termo) | Q(endereco__icontains=termo))
        for parada in paradas.order_by("-criado_em")[:24]:
            adicionar_empresa(parada.empresa, parada.endereco)
            if len(resultados) >= 12:
                break
    return JsonResponse({"resultados": resultados})
