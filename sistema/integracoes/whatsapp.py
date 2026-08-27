import json
import logging
from dataclasses import dataclass
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from sistema.models import Reuniao


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoEnvioWhatsApp:
    sucesso: bool
    status_http: int | None = None
    mensagem_id: str = ""
    erro: str = ""


def normalizar_telefone_whatsapp(numero, codigo_pais_padrao=None):
    valor_original = str(numero or "").strip()
    if not valor_original:
        return ""

    codigo_pais = str(
        codigo_pais_padrao
        or getattr(settings, "WHATSAPP_CLOUD_API_DEFAULT_COUNTRY_CODE", "55")
    ).strip()
    codigo_pais = "".join(caractere for caractere in codigo_pais if caractere.isdigit())

    telefone = "".join(caractere for caractere in valor_original if caractere.isdigit())
    prefixo_internacional = valor_original.startswith("+") or telefone.startswith("00")
    if telefone.startswith("00"):
        telefone = telefone[2:]

    if not prefixo_internacional and len(telefone) in {10, 11}:
        telefone = f"{codigo_pais}{telefone}"

    if not 8 <= len(telefone) <= 15:
        return ""
    return telefone


def _mascarar_telefone(telefone):
    if len(telefone) <= 6:
        return "*" * len(telefone)
    return f"{telefone[:4]}{'*' * (len(telefone) - 6)}{telefone[-2:]}"


def _obter_erro_meta(corpo):
    try:
        dados = json.loads(corpo)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "resposta sem detalhes"

    erro = dados.get("error") or {}
    mensagem = str(erro.get("message") or "erro nao informado pela Meta")
    codigo = erro.get("code")
    return f"{mensagem} (codigo {codigo})" if codigo is not None else mensagem


def _configuracao_incompleta():
    campos = {
        "versao da Graph API": settings.WHATSAPP_CLOUD_API_VERSION,
        "token de acesso": settings.WHATSAPP_CLOUD_API_ACCESS_TOKEN,
        "ID do numero": settings.WHATSAPP_CLOUD_API_PHONE_NUMBER_ID,
        "nome do template": settings.WHATSAPP_CLOUD_API_TEMPLATE_NAME,
        "idioma do template": settings.WHATSAPP_CLOUD_API_TEMPLATE_LANGUAGE,
    }
    return [nome for nome, valor in campos.items() if not valor]


def _montar_parametros_template(reuniao, participante):
    local = reuniao.sala.localizacao or reuniao.sala.nome
    valores = {
        "nome": participante.nome,
        "data": reuniao.data.strftime("%d/%m/%Y"),
        "horario": (
            f"{reuniao.hora_inicio.strftime('%H:%M')} as "
            f"{reuniao.hora_fim.strftime('%H:%M')}"
        ),
        "assunto": reuniao.titulo,
        "local": local,
        "descricao": reuniao.descricao or "Sem descricao informada",
    }

    parametros = []
    for campo in settings.WHATSAPP_CLOUD_API_TEMPLATE_FIELDS:
        if campo not in valores:
            raise ValueError(f"campo de template nao suportado: {campo}")
        parametros.append(valores[campo])
    return parametros


def enviar_template_whatsapp(telefone, parametros=None):
    faltantes = _configuracao_incompleta()
    if faltantes:
        return ResultadoEnvioWhatsApp(
            sucesso=False,
            erro="configuracao incompleta: " + ", ".join(faltantes),
        )

    endpoint = (
        f"{settings.WHATSAPP_CLOUD_API_BASE_URL.rstrip('/')}"
        f"/{settings.WHATSAPP_CLOUD_API_VERSION.strip('/')}"
        f"/{settings.WHATSAPP_CLOUD_API_PHONE_NUMBER_ID}/messages"
    )
    template = {
        "name": settings.WHATSAPP_CLOUD_API_TEMPLATE_NAME,
        "language": {"code": settings.WHATSAPP_CLOUD_API_TEMPLATE_LANGUAGE},
    }
    if parametros:
        template["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(parametro)}
                    for parametro in parametros
                ],
            }
        ]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone,
        "type": "template",
        "template": template,
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.WHATSAPP_CLOUD_API_ACCESS_TOKEN}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.WHATSAPP_CLOUD_API_REQUEST_TIMEOUT) as response:
            status_http = response.getcode()
            dados = json.loads(response.read().decode("utf-8") or "{}")
        mensagens = dados.get("messages") or []
        mensagem_id = str(mensagens[0].get("id") or "") if mensagens else ""
        return ResultadoEnvioWhatsApp(
            sucesso=200 <= status_http < 300,
            status_http=status_http,
            mensagem_id=mensagem_id,
        )
    except HTTPError as erro:
        corpo = erro.read().decode("utf-8", errors="replace")
        return ResultadoEnvioWhatsApp(
            sucesso=False,
            status_http=erro.code,
            erro=_obter_erro_meta(corpo),
        )
    except (URLError, TimeoutError, SocketTimeout) as erro:
        motivo = getattr(erro, "reason", erro)
        return ResultadoEnvioWhatsApp(sucesso=False, erro=f"falha de conexao: {motivo}")
    except (ValueError, json.JSONDecodeError) as erro:
        return ResultadoEnvioWhatsApp(sucesso=False, erro=f"resposta invalida: {erro}")


def notificar_reuniao_criada_whatsapp(reuniao_id):
    resumo = {"enviados": 0, "ignorados": 0, "falhas": 0, "mensagens_ids": []}
    if not settings.WHATSAPP_CLOUD_API_ENABLED:
        return resumo

    try:
        reuniao = Reuniao.objects.select_related("sala").prefetch_related("participantes").get(
            pk=reuniao_id
        )
    except Reuniao.DoesNotExist:
        logger.error("WhatsApp: reuniao %s nao encontrada apos o commit", reuniao_id)
        resumo["falhas"] += 1
        return resumo

    telefones_processados = set()
    for participante in reuniao.participantes.all():
        telefone = normalizar_telefone_whatsapp(participante.whatsapp)
        if not telefone or telefone in telefones_processados:
            resumo["ignorados"] += 1
            continue
        telefones_processados.add(telefone)

        try:
            parametros = _montar_parametros_template(reuniao, participante)
            resultado = enviar_template_whatsapp(telefone, parametros)
        except Exception as erro:
            resultado = ResultadoEnvioWhatsApp(sucesso=False, erro=str(erro))

        telefone_log = _mascarar_telefone(telefone)
        if resultado.sucesso:
            resumo["enviados"] += 1
            if resultado.mensagem_id:
                resumo["mensagens_ids"].append(resultado.mensagem_id)
            logger.info(
                "WhatsApp: reuniao %s enviada para %s, HTTP %s, mensagem %s",
                reuniao.pk,
                telefone_log,
                resultado.status_http,
                resultado.mensagem_id or "sem identificador",
            )
        else:
            resumo["falhas"] += 1
            logger.error(
                "WhatsApp: falha ao enviar reuniao %s para %s, HTTP %s: %s",
                reuniao.pk,
                telefone_log,
                resultado.status_http or "indisponivel",
                resultado.erro,
            )

    return resumo
