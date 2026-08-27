import hashlib
from functools import partial

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from sistema.integracoes.whatsapp import notificar_reuniao_criada_whatsapp
from sistema.models import ModuloSistema, Notificacao, Participante, Reuniao, ReuniaoLog
from sistema.permissions import usuario_eh_admin, usuario_pode_editar


def identificadores_usuario(usuario):
    identificadores = {usuario.username, usuario.email}
    nome_completo = usuario.get_full_name().strip()
    if nome_completo:
        identificadores.add(nome_completo)
    return {valor for valor in identificadores if valor}


def concluir_reunioes_expiradas():
    agora = timezone.localtime()
    Reuniao.objects.filter(
        Q(data__lt=agora.date()) | Q(data=agora.date(), hora_fim__lte=agora.time()),
        status=Reuniao.Status.AGENDADA,
    ).update(status=Reuniao.Status.REALIZADA)


def obter_reunioes_do_usuario(usuario, incluir_encerradas=False):
    concluir_reunioes_expiradas()
    queryset = Reuniao.objects.select_related("sala", "organizador_usuario").prefetch_related("participantes")

    filtros = Q()
    for identificador in identificadores_usuario(usuario):
        filtros |= Q(organizador__iexact=identificador)

    filtros |= Q(organizador_usuario=usuario)

    if usuario.email:
        filtros |= Q(participantes__email__iexact=usuario.email)

    queryset = queryset.filter(filtros).distinct()
    if not incluir_encerradas:
        queryset = queryset.filter(status=Reuniao.Status.AGENDADA)

    return queryset.order_by("data", "hora_inicio")


def gerar_fingerprint_reuniao(dados_post, usuario):
    campos = [
        str(usuario.pk),
        dados_post.get("titulo", "").strip(),
        dados_post.get("descricao", "").strip(),
        dados_post.get("data", "").strip(),
        dados_post.get("hora_inicio", "").strip(),
        dados_post.get("hora_fim", "").strip(),
        dados_post.get("sala", "").strip(),
        dados_post.get("status", "").strip(),
        dados_post.get("novo_participante_nome", "").strip(),
        dados_post.get("novo_participante_email", "").strip(),
        dados_post.get("novo_participante_whatsapp", "").strip(),
        "|".join(sorted(dados_post.getlist("participantes"))),
    ]
    return hashlib.sha256("||".join(campos).encode("utf-8")).hexdigest()


def criar_log_reuniao(reuniao, usuario, acao, descricao):
    ReuniaoLog.objects.create(
        reuniao=reuniao if acao != ReuniaoLog.Acao.EXCLUSAO else None,
        reuniao_titulo=reuniao.titulo,
        usuario=usuario,
        acao=acao,
        descricao=descricao,
    )


def vincular_novo_participante(form, reuniao):
    novo_nome = (form.cleaned_data.get("novo_participante_nome") or "").strip()
    novo_email = (form.cleaned_data.get("novo_participante_email") or "").strip()
    novo_whatsapp = (form.cleaned_data.get("novo_participante_whatsapp") or "").strip()

    if not novo_nome:
        return

    participante = None
    usuario = None
    if novo_email:
        participante = Participante.objects.filter(email__iexact=novo_email).first()
        usuario = reuniao.organizador_usuario.__class__.objects.filter(email__iexact=novo_email).first()
    else:
        participante = Participante.objects.filter(
            nome__iexact=novo_nome,
            email__isnull=True,
        ).first()

    if participante:
        if not participante.nome:
            participante.nome = novo_nome
        elif novo_nome and participante.nome != novo_nome:
            participante.nome = novo_nome
        if novo_email and not participante.email:
            participante.email = novo_email
        if novo_whatsapp and participante.whatsapp != novo_whatsapp:
            participante.whatsapp = novo_whatsapp
        if not participante.usuario:
            participante.usuario = usuario
        participante.save()
    else:
        participante = Participante.objects.create(
            nome=novo_nome,
            email=novo_email or None,
            whatsapp=novo_whatsapp,
            usuario=usuario,
        )
    reuniao.participantes.add(participante)


def agendar_whatsapp_reuniao_criada(reuniao):
    transaction.on_commit(partial(notificar_reuniao_criada_whatsapp, reuniao.pk))


def notificar_participantes_reuniao(reuniao, tipo, autor):
    if tipo == "criacao":
        titulo = f"Nova reuniao: {reuniao.titulo}"
        mensagem = "Voce foi incluido em uma nova reuniao na agenda corporativa."
    elif tipo == "cancelamento":
        titulo = f"Reuniao cancelada: {reuniao.titulo}"
        mensagem = "A reuniao em que voce estava listado foi cancelada."
    else:
        titulo = f"Reuniao atualizada: {reuniao.titulo}"
        mensagem = "Houve uma atualizacao em uma reuniao da sua agenda."

    usuarios = []
    for participante in reuniao.participantes.all():
        if participante.usuario_id:
            usuarios.append(participante.usuario)
            continue
        if not participante.email:
            continue
        usuario = autor.__class__.objects.filter(email__iexact=participante.email).first()
        if usuario:
            participante.usuario = usuario
            participante.save(update_fields=["usuario"])
            usuarios.append(usuario)

    for usuario in usuarios:
        if autor and usuario.pk == autor.pk:
            continue
        Notificacao.objects.create(
            destinatario=usuario,
            modulo=ModuloSistema.AGENDA,
            titulo=titulo,
            mensagem=mensagem,
            url_destino=reverse("detalhe_reuniao", args=[reuniao.pk]),
        )


def usuario_pode_gerenciar_reuniao(usuario, reuniao):
    if not usuario_pode_editar(usuario, ModuloSistema.AGENDA):
        return False
    if usuario_eh_admin(usuario, ModuloSistema.AGENDA):
        return True
    if reuniao.organizador_usuario_id == usuario.pk:
        return True
    return reuniao.organizador in identificadores_usuario(usuario)
