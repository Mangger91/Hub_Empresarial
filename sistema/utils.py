from datetime import datetime
from email.utils import formataddr
from email.mime.image import MIMEImage
from pathlib import Path
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


def montar_dados_aviso_reuniao(reuniao):
    participantes = list(reuniao.participantes.all())
    nomes_participantes = ", ".join(
        participante.nome.strip()
        for participante in participantes
        if participante.nome and participante.nome.strip()
    )
    return {
        "data": reuniao.data.strftime("%d/%m/%Y"),
        "horario": (
            f"{reuniao.hora_inicio.strftime('%H:%M')} às "
            f"{reuniao.hora_fim.strftime('%H:%M')}"
        ),
        "assunto": reuniao.titulo,
        "local": reuniao.sala.nome,
        "participantes": nomes_participantes or "Não informados",
        "responsavel_ata": reuniao.responsavel_ata.strip() or "Não informado",
    }


def _cabecalho_aviso_reuniao(tipo, data_formatada):
    if tipo == "cancelamento":
        return f"AVISO DE CANCELAMENTO DA REUNIÃO DO DIA {data_formatada}."
    if tipo == "edicao":
        return f"SEGUE ABAIXO ATUALIZAÇÃO DA REUNIÃO DO DIA {data_formatada}."
    return f"SEGUE ABAIXO LEMBRETE DE REUNIÕES DO DIA {data_formatada}."


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
            <div style="font-weight:700; color:#202124;">FALAVINHA INTELIGÊNCIA CONTÁBIL</div>
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
            alt="Assinatura Falavinha Inteligencia Contabil"
            style="display:block; width:100%; max-width:820px; height:auto; border:0; outline:none; text-decoration:none;"
        >
    </div>
    """


def _montar_assinatura_texto():
    return (
        "\n\n--\n"
        "FALAVINHA INTELIGÊNCIA CONTÁBIL\n"
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

    dados = montar_dados_aviso_reuniao(reuniao)
    cabecalho = _cabecalho_aviso_reuniao(tipo, dados["data"])

    if tipo == "cancelamento":
        assunto = f"Cancelamento de reunião: {reuniao.titulo}"
        badge_texto = "Reuniao cancelada"
    elif tipo == "edicao":
        assunto = f"Atualização de reunião: {reuniao.titulo}"
        badge_texto = "Reuniao atualizada"
    else:
        assunto = f"Lembrete de reunião: {reuniao.titulo}"
        badge_texto = "Lembrete de reuniao"

    mensagem_texto = (
        f"{cabecalho}\n\n"
        f"Horário: {dados['horario']}\n"
        f"Assunto: {dados['assunto']}\n"
        f"Local: {dados['local']}\n"
        f"Participantes: {dados['participantes']}\n"
        "Responsável pela elaboração e entrega da ata: "
        f"{dados['responsavel_ata']}"
        f"{_montar_assinatura_texto()}"
    )

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
                        <h2 style="margin:0; font-size:24px; line-height:1.35; color:#202124;">📌 {_formatar_texto_email(cabecalho)}</h2>
                    </td>
                </tr>
                <tr>
                    <td style="padding:0 36px 26px;">
                        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%; border-collapse:collapse;">
                            <tr>
                                <td style="padding:12px 0; width:230px; font-weight:700; color:#1a73e8; vertical-align:top;">Horário</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(dados['horario'])}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Assunto</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(dados['assunto'])}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Local</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(dados['local'])}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Participantes</td>
                                <td style="padding:12px 0; color:#202124; line-height:1.6;">{_formatar_texto_email(dados['participantes'])}</td>
                            </tr>
                            <tr>
                                <td style="padding:12px 0; font-weight:700; color:#1a73e8; vertical-align:top;">Responsável pela elaboração e entrega da ata</td>
                                <td style="padding:12px 0; color:#202124;">{_formatar_texto_email(dados['responsavel_ata'])}</td>
                            </tr>
                        </table>

                        <p style="margin:22px 0 0; padding:16px 18px; border-left:4px solid #1a73e8; background:#f8fbff; color:#5f6368; line-height:1.6;">
                            Mensagem automática. O convite de calendário segue anexado para facilitar o aceite e o salvamento do compromisso.
                        </p>

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
