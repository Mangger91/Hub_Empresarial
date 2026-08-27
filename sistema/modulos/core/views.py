from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from sistema.models import ItemEstoque, ModuloSistema, Notificacao, Reuniao
from sistema.permissions import MODULOS_SISTEMA, montar_menu

from ..agenda.services import obter_reunioes_do_usuario
from ..common import renderizar_modulo_sem_permissao


@login_required
def inicio(request):
    hoje = timezone.localdate()
    reunioes = obter_reunioes_do_usuario(request.user)
    itens_estoque = ItemEstoque.objects.filter(ativo=True)
    itens_criticos = itens_estoque.filter(
        Q(quantidade_atual__lte=0)
        | Q(estoque_minimo__gt=0, quantidade_atual__lt=F("estoque_minimo"))
    )
    modulos_liberados = [modulo for modulo in montar_menu(request.user) if modulo["possui_acesso"]]
    context = {
        "modulo_titulo": "Inicio",
        "modulo_descricao": "Acesso rapido aos principais fluxos do sistema interno.",
        "ocultar_botoes_voltar": True,
        "atalhos_modulos": modulos_liberados[:6],
        "total_modulos": len(modulos_liberados),
        "reunioes_hoje": reunioes.filter(data=hoje, status=Reuniao.Status.AGENDADA).count(),
        "reunioes_semana": reunioes.filter(
            data__gte=hoje,
            data__lte=hoje + timedelta(days=7),
            status=Reuniao.Status.AGENDADA,
        ).count(),
        "estoque_alertas": itens_criticos.count(),
        "notificacoes_recentes": request.user.notificacoes.all()[:4],
    }
    return render(request, "sistema/inicio.html", context)


@login_required
def dashboard(request):
    reunioes = obter_reunioes_do_usuario(request.user)
    itens_estoque = ItemEstoque.objects.filter(ativo=True)
    context = {
        "modulos": MODULOS_SISTEMA,
        "total_reunioes": reunioes.count(),
        "proximas_reunioes": reunioes.filter(
            data__gte=date.today(),
            status=Reuniao.Status.AGENDADA,
        ).count(),
        "itens_estoque_baixo": itens_estoque.filter(quantidade_atual__lte=0).count()
        + sum(1 for item in itens_estoque if item.estoque_baixo and item.quantidade_atual > 0),
        "notificacoes_recentes": request.user.notificacoes.all()[:5],
        "ocultar_botoes_voltar": True,
    }
    return render(request, "sistema/dashboard.html", context)


@login_required
def central_notificacoes(request):
    notificacoes = request.user.notificacoes.all()
    return render(
        request,
        "sistema/notificacoes.html",
        {
            "notificacoes": notificacoes,
            "modulo_titulo": "Notificacoes",
            "modulo_descricao": "Avisos internos sobre agenda e operacoes do sistema.",
        },
    )


@login_required
def abrir_notificacao(request, pk):
    notificacao = get_object_or_404(Notificacao, pk=pk, destinatario=request.user)
    if not notificacao.lida:
        notificacao.lida = True
        notificacao.lida_em = timezone.now()
        notificacao.save(update_fields=["lida", "lida_em"])
    if notificacao.url_destino:
        return redirect(notificacao.url_destino)
    return redirect("central_notificacoes")


@login_required
def modulo_placeholder(request, modulo, titulo, descricao):
    return renderizar_modulo_sem_permissao(
        request,
        modulo,
        titulo,
        descricao,
        "sistema/modulo_placeholder.html",
    )


@login_required
def avaliacao_colaboradores(request):
    return modulo_placeholder(
        request,
        ModuloSistema.AVALIACAO,
        "Avaliacao de Colaboradores",
        "Base pronta para evoluirmos ciclos, metas, feedbacks e historico por colaborador.",
    )


@login_required
def chamados_ti(request):
    return modulo_placeholder(
        request,
        ModuloSistema.CHAMADOS_TI,
        "Chamados - TI",
        "Espaco inicial para fila de chamados, prioridades e acompanhamento de resolucao.",
    )
