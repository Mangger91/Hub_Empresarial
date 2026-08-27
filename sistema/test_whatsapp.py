from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from sistema.integracoes.whatsapp import (
    ResultadoEnvioWhatsApp,
    enviar_template_whatsapp,
    normalizar_telefone_whatsapp,
)
from sistema.models import Participante, PerfilUsuario, Reuniao, Sala


User = get_user_model()


CONFIGURACAO_WHATSAPP_TESTE = {
    "WHATSAPP_CLOUD_API_ENABLED": True,
    "WHATSAPP_CLOUD_API_BASE_URL": "https://graph.facebook.com",
    "WHATSAPP_CLOUD_API_VERSION": "v99.0",
    "WHATSAPP_CLOUD_API_ACCESS_TOKEN": "token-apenas-de-teste",
    "WHATSAPP_CLOUD_API_PHONE_NUMBER_ID": "123456789",
    "WHATSAPP_CLOUD_API_TEMPLATE_NAME": "aviso_reuniao",
    "WHATSAPP_CLOUD_API_TEMPLATE_LANGUAGE": "pt_BR",
    "WHATSAPP_CLOUD_API_TEMPLATE_FIELDS": [
        "nome",
        "data",
        "horario",
        "assunto",
        "local",
    ],
    "WHATSAPP_CLOUD_API_DEFAULT_COUNTRY_CODE": "55",
    "WHATSAPP_CLOUD_API_REQUEST_TIMEOUT": 2,
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DEFAULT_FROM_EMAIL": "agenda@example.com",
    "CALENDAR_INVITE_FROM_EMAIL": "agenda@example.com",
    "CALENDAR_REPLY_TO_EMAIL": "agenda@example.com",
    "CALENDAR_ORGANIZER_EMAIL": "agenda@example.com",
}


class NormalizacaoWhatsAppTests(TestCase):
    def test_adiciona_codigo_do_brasil_quando_usuario_informa_ddd(self):
        self.assertEqual(normalizar_telefone_whatsapp("(41) 99999-9999"), "5541999999999")

    def test_preserva_numero_internacional_com_prefixo(self):
        self.assertEqual(normalizar_telefone_whatsapp("+1 650 555 1234"), "16505551234")

    def test_rejeita_numero_curto(self):
        self.assertEqual(normalizar_telefone_whatsapp("1234"), "")


@override_settings(**CONFIGURACAO_WHATSAPP_TESTE)
class ClienteWhatsAppCloudApiTests(TestCase):
    @patch("sistema.integracoes.whatsapp.urlopen")
    def test_captura_status_e_identificador_retornados_pela_meta(self, urlopen_mock):
        resposta = MagicMock()
        resposta.getcode.return_value = 200
        resposta.read.return_value = b'{"messages": [{"id": "wamid.resposta-meta"}]}'
        urlopen_mock.return_value.__enter__.return_value = resposta

        resultado = enviar_template_whatsapp(
            "5541999999999",
            ["Ana", "01/09/2026", "09:00 as 10:00", "Planejamento", "Sala 1"],
        )

        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.status_http, 200)
        self.assertEqual(resultado.mensagem_id, "wamid.resposta-meta")
        requisicao = urlopen_mock.call_args.args[0]
        self.assertEqual(
            requisicao.full_url,
            "https://graph.facebook.com/v99.0/123456789/messages",
        )


@override_settings(**CONFIGURACAO_WHATSAPP_TESTE)
class ReuniaoWhatsAppTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(
            nome="Sala Diretoria",
            localizacao="Segundo andar",
            capacidade=8,
        )
        self.usuario = User.objects.create_user(
            username="agenda-whatsapp",
            email="agenda.whatsapp@empresa.com.br",
            password="Senha12345",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=self.usuario)
        perfil.papel_agenda = "ADMINISTRADOR"
        perfil.save()
        self.client.login(username=self.usuario.email, password="Senha12345")

    def dados_reuniao(self, participantes):
        return {
            "titulo": "Reuniao de planejamento",
            "descricao": "Definicao das prioridades",
            "data": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "hora_inicio": "09:00",
            "hora_fim": "10:00",
            "sala": str(self.sala.pk),
            "status": Reuniao.Status.AGENDADA,
            "participantes": [str(participante.pk) for participante in participantes],
        }

    def criar_reuniao_executando_pos_commit(self, participantes):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("nova_reuniao"),
                self.dados_reuniao(participantes),
            )

    @patch("sistema.integracoes.whatsapp.enviar_template_whatsapp")
    def test_participante_com_whatsapp_recebe_email_e_dispara_api(self, enviar_mock):
        enviar_mock.return_value = ResultadoEnvioWhatsApp(
            sucesso=True,
            status_http=200,
            mensagem_id="wamid.teste-1",
        )
        participante = Participante.objects.create(
            nome="Ana",
            email="ana@example.com",
            whatsapp="41999999999",
        )

        resposta = self.criar_reuniao_executando_pos_commit([participante])

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Reuniao.objects.filter(titulo="Reuniao de planejamento").exists())
        self.assertEqual(len(mail.outbox), 1)
        enviar_mock.assert_called_once()
        self.assertEqual(enviar_mock.call_args.args[0], "5541999999999")

    @patch("sistema.integracoes.whatsapp.enviar_template_whatsapp")
    def test_participante_sem_whatsapp_recebe_email_e_api_e_ignorada(self, enviar_mock):
        participante = Participante.objects.create(
            nome="Bruno",
            email="bruno@example.com",
        )

        resposta = self.criar_reuniao_executando_pos_commit([participante])

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Reuniao.objects.filter(titulo="Reuniao de planejamento").exists())
        self.assertEqual(len(mail.outbox), 1)
        enviar_mock.assert_not_called()

    @patch("sistema.integracoes.whatsapp.enviar_template_whatsapp")
    def test_erro_da_meta_nao_impede_reuniao_nem_email(self, enviar_mock):
        enviar_mock.return_value = ResultadoEnvioWhatsApp(
            sucesso=False,
            status_http=400,
            erro="template invalido",
        )
        participante = Participante.objects.create(
            nome="Carla",
            email="carla@example.com",
            whatsapp="41988887777",
        )

        resposta = self.criar_reuniao_executando_pos_commit([participante])

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Reuniao.objects.filter(titulo="Reuniao de planejamento").exists())
        self.assertEqual(len(mail.outbox), 1)
        enviar_mock.assert_called_once()

    @patch("sistema.integracoes.whatsapp.enviar_template_whatsapp")
    def test_varios_participantes_enviam_somente_para_telefones_validos(self, enviar_mock):
        enviar_mock.return_value = ResultadoEnvioWhatsApp(
            sucesso=True,
            status_http=200,
            mensagem_id="wamid.teste-multiplo",
        )
        participantes = [
            Participante.objects.create(
                nome="Daniel",
                email="daniel@example.com",
                whatsapp="41977776666",
            ),
            Participante.objects.create(
                nome="Elisa",
                email="elisa@example.com",
                whatsapp="1234",
            ),
            Participante.objects.create(
                nome="Fabio",
                email="fabio@example.com",
            ),
        ]

        resposta = self.criar_reuniao_executando_pos_commit(participantes)

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        enviar_mock.assert_called_once()
        self.assertEqual(enviar_mock.call_args.args[0], "5541977776666")

    @patch("sistema.integracoes.whatsapp.enviar_template_whatsapp")
    def test_participante_manual_tem_whatsapp_normalizado(self, enviar_mock):
        enviar_mock.return_value = ResultadoEnvioWhatsApp(
            sucesso=True,
            status_http=200,
            mensagem_id="wamid.teste-manual",
        )
        dados = self.dados_reuniao([])
        dados.update(
            {
                "novo_participante_nome": "Helena",
                "novo_participante_email": "helena@example.com",
                "novo_participante_whatsapp": "(41) 95555-4444",
            }
        )

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.post(reverse("nova_reuniao"), dados)

        participante = Participante.objects.get(email="helena@example.com")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(participante.whatsapp, "5541955554444")
        enviar_mock.assert_called_once()

    @patch("sistema.integracoes.whatsapp.enviar_template_whatsapp")
    def test_edicao_da_reuniao_nao_dispara_whatsapp(self, enviar_mock):
        participante = Participante.objects.create(
            nome="Gabriela",
            email="gabriela@example.com",
            whatsapp="41966665555",
        )
        reuniao = Reuniao.objects.create(
            titulo="Reuniao original",
            descricao="Pauta original",
            data=timezone.localdate() + timedelta(days=3),
            hora_inicio="14:00",
            hora_fim="15:00",
            sala=self.sala,
            organizador=self.usuario.email,
            organizador_usuario=self.usuario,
        )
        reuniao.participantes.add(participante)
        dados = self.dados_reuniao([participante])
        dados["titulo"] = "Reuniao editada"

        resposta = self.client.post(reverse("editar_reuniao", args=[reuniao.pk]), dados)

        self.assertEqual(resposta.status_code, 302)
        enviar_mock.assert_not_called()
