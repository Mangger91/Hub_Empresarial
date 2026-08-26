import json
from datetime import datetime
from email.utils import formataddr
from email.mime.image import MIMEImage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import escape


TIMEZONE_REUNIAO = ZoneInfo("America/Sao_Paulo")
ASSINATURA_PATH = Path(settings.BASE_DIR) / "static" / "Assinatura.png"
ASSINATURA_CID = "assinatura-falavinha"


def _formatar_texto_email(texto):
    return escape(texto or "")


def _escapar_ics(texto):
    return (
        (texto or "")
        .replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace(",", r"\,")
        .replace(";", r"\;")
    )


def _montar_datas_reuniao(reuniao):
    inicio = datetime.combine(reuniao.data, reuniao.hora_inicio, tzinfo=TIMEZONE_REUNIAO)
    fim = datetime.combine(reuniao.data, reuniao.hora_fim, tzinfo=TIMEZONE_REUNIAO)
    return inicio, fim


def _normalizar_whatsapp(numero):
    telefone = "".join(caractere for caractere in str(numero or "") if caractere.isdigit())
    if len(telefone) in {10, 11}:
        return f"55{telefone}"
    return telefone


def _gerar_uid_reuniao(reuniao):
    return f"reuniao-{reuniao.pk}@agenda-reunioes.local"


def _gerar_convite_ics(reuniao, emails, tipo):
    inicio, fim = _montar_datas_reuniao(reuniao)
    criado_em = timezone.now().astimezone(TIMEZONE_REUNIAO)
    method = "CANCEL" if tipo == "cancelamento" else "REQUEST"
    status = "CANCELLED" if tipo == "cancelamento" else "CONFIRMED"
    sequence = int(reuniao.atualizada_em.timestamp()) if reuniao.atualizada_em else int(criado_em.timestamp())
    descricao = reuniao.descricao or "Sem descrição informada."
    localizacao = reuniao.sala.localizacao or reuniao.sala.nome

    participantes_ics = []
    for email in emails:
        participantes_ics.append(
            "ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN={nome}:MAILTO:{email}".format(
                nome=_escapar_ics(email),
                email=email,
            )
        )

    linhas = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Falavinha//Agenda de Reuniões//PT-BR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{_gerar_uid_reuniao(reuniao)}",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{criado_em.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
        f"CREATED:{criado_em.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
        f"LAST-MODIFIED:{criado_em.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{inicio.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{fim.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{_escapar_ics(reuniao.titulo)}",
        f"DESCRIPTION:{_escapar_ics(descricao)}",
        f"LOCATION:{_escapar_ics(localizacao)}",
        f"STATUS:{status}",
        "TRANSP:OPAQUE",
        "CLASS:PUBLIC",
        f"ORGANIZER;CN={_escapar_ics(settings.CALENDAR_ORGANIZER_NAME)}:MAILTO:{settings.CALENDAR_ORGANIZER_EMAIL}",
        "X-MICROSOFT-CDO-BUSYSTATUS:BUSY",
        "BEGIN:VALARM",
        "TRIGGER:-PT30M",
        "ACTION:DISPLAY",
        "DESCRIPTION:Lembrete de reunião",
        "END:VALARM",
    ]

    linhas.extend(participantes_ics)
    linhas.extend(["END:VEVENT", "END:VCALENDAR"])
    return method, "\r\n".join(linhas)


def _montar_assinatura_html():
    if not ASSINATURA_PATH.exists():
        return """
        <div style="margin-top:28px; padding-top:18px; border-top:1px solid #d9d9d9; font-size:13px; color:#5f6368;">
            <div style="font-weight:700; color:#202124;">ROBERTO MANGGER JUNIOR | SISTEMAS</div>
            <div>Falavinha Inteligência Contábil</div>
            <div>Rua Camões, 1753 - Hugo Lange - Curitiba - PR</div>
            <div>(41) 3030 7575</div>
            <div>www.falavinhacontabil.com.br</div>
            <div>falavinha@falavinhacontabil.com.br</div>
        </div>
        """

    return f"""
    <div style="margin-top:28px; padding-top:18px; border-top:1px solid #d9d9d9;">
        <img
            src="cid:{ASSINATURA_CID}"
            alt="Assinatura Roberto Mangger Junior"
            style="display:block; width:100%; max-width:820px; height:auto; border:0; outline:none; text-decoration:none;"
        >
    </div>
    """


def _montar_assinatura_texto():
    return (
        "\n\n--\n"
        "ROBERTO MANGGER JUNIOR | SISTEMAS\n"
        "Falavinha Inteligência Contábil\n"
        "Rua Camões, 1753 - Hugo Lange - Curitiba - PR\n"
        "(41) 3030 7575\n"
        "www.falavinhacontabil.com.br\n"
        "falavinha@falavinhacontabil.com.br\n"
        "Este é um disparo automático do sistema de agenda de reuniões."
    )


def _anexar_assinatura_inline(email):
    if not ASSINATURA_PATH.exists():
        return

    with ASSINATURA_PATH.open("rb") as imagem_file:
        imagem = MIMEImage(imagem_file.read())

    imagem.add_header("Content-ID", f"<{ASSINATURA_CID}>")
    imagem.add_header("Content-Disposition", "inline", filename=ASSINATURA_PATH.name)
    email.attach(imagem)


def _remetente_calendario():
    email = (settings.CALENDAR_INVITE_FROM_EMAIL or settings.DEFAULT_FROM_EMAIL or "").strip()
    if not email:
        raise RuntimeError(
            "remetente de e-mail nao configurado; defina DJANGO_DEFAULT_FROM_EMAIL ou DJANGO_CALENDAR_INVITE_FROM_EMAIL"
        )
    return formataddr((settings.CALENDAR_ORGANIZER_NAME, email))


def _reply_to_calendario():
    email = (settings.CALENDAR_REPLY_TO_EMAIL or settings.DEFAULT_FROM_EMAIL or "").strip()
    return [email] if email else []


def enviar_email_reuniao(reuniao, tipo="criacao"):
    participantes = list(reuniao.participantes.all())
    emails = [participante.email for participante in participantes if participante.email]

    if not emails:
        return False

    data_formatada = reuniao.data.strftime("%d/%m/%Y")
    hora_inicio = reuniao.hora_inicio.strftime("%H:%M")
    hora_fim = reuniao.hora_fim.strftime("%H:%M")
    organizador = getattr(reuniao, "nome_organizador", None) or reuniao.organizador or "Nao informado"
    localizacao = reuniao.sala.localizacao or "Não informada"
    descricao = reuniao.descricao or "Sem descrição informada."

    if tipo == "criacao":
        assunto = f"Convite de reunião: {reuniao.titulo}"
        titulo_acao = "Uma nova reunião foi agendada"
        intro_texto = "Você recebeu um convite de reunião. Se o seu cliente de e-mail suportar convites de calendário, basta aceitar para salvar o compromisso na sua agenda."
        badge_texto = "Convite de calendário"
    elif tipo == "edicao":
        assunto = f"Atualização de reunião: {reuniao.titulo}"
        titulo_acao = "Uma reunião foi atualizada"
        intro_texto = "Os dados desta reunião foram atualizados. Aceite ou atualize o convite para refletir as mudanças no seu calendário."
        badge_texto = "Convite atualizado"
    elif tipo == "cancelamento":
        assunto = f"Cancelamento de reunião: {reuniao.titulo}"
        titulo_acao = "Uma reunião foi cancelada"
        intro_texto = "Esta mensagem confirma o cancelamento da reunião. O convite de calendário acompanha esta atualização."
        badge_texto = "Convite cancelado"
    else:
        assunto = f"Atualização de reunião: {reuniao.titulo}"
        titulo_acao = "Houve uma atualização na reunião"
        intro_texto = "Confira abaixo os dados mais recentes da reunião."
        badge_texto = "Atualização"

    linhas_participantes = "\n".join(
        f"- {participante.nome} ({participante.email})" for participante in participantes
    ) or "Nenhum participante informado."

    mensagem_texto = (
        f"{titulo_acao}\n\n"
        f"{intro_texto}\n\n"
        f"Título: {reuniao.titulo}\n"
        f"Descrição: {descricao}\n"
        f"Data: {data_formatada}\n"
        f"Horário: {hora_inicio} às {hora_fim}\n"
        f"Sala: {reuniao.sala.nome}\n"
        f"Localização: {localizacao}\n"
        f"Organizador: {organizador}\n"
        f"Status: {reuniao.get_status_display()}\n\n"
        f"Participantes:\n{linhas_participantes}"
        f"{_montar_assinatura_texto()}"
    )

    lista_participantes_html = "".join(
        f"<li style='margin-bottom:6px; color:#202124;'>{_formatar_texto_email(participante.nome)} ({_formatar_texto_email(participante.email)})</li>"
        for participante in participantes
    ) or "<li style='color:#202124;'>Nenhum participante informado.</li>"

    mensagem_html = f"""
    <html>
        <body style="margin:0; padding:24px; background:#f1f3f4; font-family:Arial, Helvetica, sans-serif; color:#202124;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:840px; margin:0 auto; background:#ffffff; border:1px solid #dadce0; border-radius:16px; overflow:hidden;">
                <tr>
                    <td style="padding:0; background:#ffffff;">
                        <div style="height:6px; background:#1a73e8;"></div>
                    </td>
                </tr>
                <tr>
                    <td style="padding:32px 36px 22px;">
                        <div style="display:inline-block; margin-bottom:16px; padding:6px 12px; border-radius:999px; background:#e8f0fe; color:#1a73e8; font-size:12px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase;">
                            {badge_texto}
                        </div>
                        <h2 style="margin:0 0 12px; font-size:30px; line-height:1.25; color:#202124;">{_formatar_texto_email(titulo_acao)}</h2>
                        <p style="margin:0; font-size:16px; line-height:1.7; color:#5f6368;">
                            {_formatar_texto_email(intro_texto)}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding:0 36px 26px;">
                        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%; border-collapse:collapse;">
                            <tr>
                                <td style="padding:12px 0; width:180px; font-weight:700; color:#1a73e8; vertical-align:top;">Título</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(reuniao.titulo)}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Descrição</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(descricao)}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Data</td>
                                <td style="padding:12px 0; color:#202124;">{data_formatada}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Horário</td>
                                <td style="padding:12px 0; color:#202124;">{hora_inicio} às {hora_fim}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Sala</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(reuniao.sala.nome)}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Localização</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(localizacao)}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Organizador</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(organizador)}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Status</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(reuniao.get_status_display())}</td>
                            </tr>
                        </table>

                        <div style="margin-top:24px; padding:20px 22px; border:1px solid #dadce0; border-radius:12px; background:#fafafa;">
                            <div style="font-size:13px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; color:#5f6368; margin-bottom:12px;">
                                Participantes
                            </div>
                            <ul style="margin:0; padding-left:18px;">
                                {lista_participantes_html}
                            </ul>
                        </div>

                        <div style="margin-top:24px; padding:18px 20px; border-left:4px solid #1a73e8; background:#f8fbff; color:#5f6368; line-height:1.65;">
                            <strong style="display:block; margin-bottom:8px; color:#202124;">Mensagem automática</strong>
                            Este é um disparo automático do sistema de agenda de reuniões. O convite de calendário segue neste e-mail para facilitar o aceite e o salvamento do compromisso na agenda.
                        </div>

                        {_montar_assinatura_html()}
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """

    email = EmailMultiAlternatives(
        subject=assunto,
        body=mensagem_texto,
        from_email=_remetente_calendario(),
        to=emails,
        reply_to=_reply_to_calendario(),
    )
    email.attach_alternative(mensagem_html, "text/html")

    method_ics, convite_ics = _gerar_convite_ics(reuniao, emails, tipo)
    email.attach_alternative(
        convite_ics,
        f"text/calendar; method={method_ics}; charset=UTF-8",
    )
    email.attach(
        filename="convite-reuniao.ics",
        content=convite_ics,
        mimetype=f"text/calendar; method={method_ics}; charset=UTF-8",
    )

    _anexar_assinatura_inline(email)
    email.send(fail_silently=False)
    return True


def _montar_mensagem_whatsapp_reuniao(reuniao, tipo):
    data_formatada = reuniao.data.strftime("%d/%m/%Y")
    hora_inicio = reuniao.hora_inicio.strftime("%H:%M")
    hora_fim = reuniao.hora_fim.strftime("%H:%M")
    sala = reuniao.sala.nome

    if tipo == "criacao":
        abertura = "Nova reuniao agendada"
    elif tipo == "edicao":
        abertura = "Reuniao atualizada"
    elif tipo == "cancelamento":
        abertura = "Reuniao cancelada"
    else:
        abertura = "Aviso de reuniao"

    return (
        f"{abertura}: {reuniao.titulo}\n"
        f"Data: {data_formatada}\n"
        f"Horario: {hora_inicio} as {hora_fim}\n"
        f"Sala: {sala}\n"
        f"Status: {reuniao.get_status_display()}"
    )


def enviar_whatsapp_reuniao(reuniao, tipo="criacao"):
    webhook_url = getattr(settings, "WHATSAPP_AGENDA_WEBHOOK_URL", "")
    if not webhook_url:
        return 0

    mensagem = _montar_mensagem_whatsapp_reuniao(reuniao, tipo)
    token = getattr(settings, "WHATSAPP_AGENDA_TOKEN", "")
    timeout = getattr(settings, "WHATSAPP_AGENDA_REQUEST_TIMEOUT", 10)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    enviados = 0
    telefones = {
        _normalizar_whatsapp(participante.whatsapp)
        for participante in reuniao.participantes.all()
        if getattr(participante, "whatsapp", "")
    }
    telefones = {telefone for telefone in telefones if telefone}

    for telefone in telefones:
        payload = {
            "to": telefone,
            "message": mensagem,
            "meeting_id": reuniao.pk,
            "type": tipo,
        }
        request = Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout):
                enviados += 1
        except HTTPError as erro:
            raise RuntimeError(f"servico de WhatsApp retornou HTTP {erro.code}") from erro
        except URLError as erro:
            raise RuntimeError(f"nao foi possivel acessar o WhatsApp: {erro.reason}") from erro
        except TimeoutError as erro:
            raise RuntimeError("o servico de WhatsApp demorou para responder") from erro

    return enviados


def obter_email_criador_reuniao(reuniao):
    if reuniao.organizador_usuario and reuniao.organizador_usuario.email:
        return reuniao.organizador_usuario.email

    if reuniao.organizador and "@" in reuniao.organizador:
        return reuniao.organizador

    return None


def enviar_email_reuniao_finalizada(reuniao):
    email_criador = obter_email_criador_reuniao(reuniao)

    if not email_criador:
        return False

    data_formatada = reuniao.data.strftime("%d/%m/%Y")
    hora_inicio = reuniao.hora_inicio.strftime("%H:%M")
    hora_fim = reuniao.hora_fim.strftime("%H:%M")
    localizacao = reuniao.sala.localizacao or "Não informada"
    organizador = getattr(reuniao, "nome_organizador", None) or reuniao.organizador or "Nao informado"

    assunto = f"Reunião finalizada: {reuniao.titulo}"
    mensagem_texto = (
        "A reunião abaixo foi finalizada.\n\n"
        f"Título: {reuniao.titulo}\n"
        f"Data: {data_formatada}\n"
        f"Horário: {hora_inicio} às {hora_fim}\n"
        f"Sala: {reuniao.sala.nome}\n"
        f"Localização: {localizacao}\n"
        f"Organizador: {organizador}\n\n"
        "Agora deverá ser feita a ATA de reuniões."
        f"{_montar_assinatura_texto()}"
    )

    mensagem_html = f"""
    <html>
        <body style="margin:0; padding:24px; background:#f1f3f4; font-family:Arial, Helvetica, sans-serif; color:#202124;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:820px; margin:0 auto; background:#ffffff; border:1px solid #dadce0; border-radius:16px; overflow:hidden;">
                <tr>
                    <td style="padding:0; background:#ffffff;">
                        <div style="height:6px; background:#0f766e;"></div>
                    </td>
                </tr>
                <tr>
                    <td style="padding:32px 36px 26px;">
                        <div style="display:inline-block; margin-bottom:16px; padding:6px 12px; border-radius:999px; background:#ccfbf1; color:#0f766e; font-size:12px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase;">
                            Reunião finalizada
                        </div>
                        <h2 style="margin:0 0 12px; font-size:30px; line-height:1.25; color:#202124;">A reunião foi concluída</h2>
                        <p style="margin:0 0 22px; font-size:16px; line-height:1.7; color:#5f6368;">
                            A reunião abaixo foi finalizada. Agora deverá ser feita a ATA de reuniões.
                        </p>

                        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%; border-collapse:collapse;">
                            <tr>
                                <td style="padding:12px 0; width:180px; font-weight:700; color:#0f766e; vertical-align:top;">Título</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(reuniao.titulo)}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#0f766e; vertical-align:top;">Data</td>
                                <td style="padding:12px 0; color:#202124;">{data_formatada}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#0f766e; vertical-align:top;">Horário</td>
                                <td style="padding:12px 0; color:#202124;">{hora_inicio} às {hora_fim}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#0f766e; vertical-align:top;">Sala</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(reuniao.sala.nome)}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#0f766e; vertical-align:top;">Localização</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(localizacao)}</td>
                            </tr>
                        </table>

                        <div style="margin-top:24px; padding:18px 20px; border-left:4px solid #0f766e; background:#f0fdfa; color:#134e4a; line-height:1.65;">
                            <strong style="display:block; margin-bottom:8px; color:#134e4a;">Próximo passo</strong>
                            Fazer a ATA de reuniões referente a este compromisso.
                        </div>

                        {_montar_assinatura_html()}
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """

    email = EmailMultiAlternatives(
        subject=assunto,
        body=mensagem_texto,
        from_email=_remetente_calendario(),
        to=[email_criador],
        reply_to=_reply_to_calendario(),
    )
    email.attach_alternative(mensagem_html, "text/html")
    _anexar_assinatura_inline(email)
    email.send(fail_silently=False)
    return True
