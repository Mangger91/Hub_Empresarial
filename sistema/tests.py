from datetime import date, timedelta, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from sistema.modulos.usuarios.forms import UsuarioSistemaForm

from .models import (
    CategoriaEstoque,
    EnderecoEmpresaMotoboy,
    ItemEstoque,
    ModuloSistema,
    MovimentacaoEstoque,
    Participante,
    PerfilUsuario,
    Reuniao,
    RotaMotoboy,
    Sala,
)


class AutenticacaoEmailTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username="mangger",
            email="mangger@empresa.com.br",
            password="SenhaForte123",
        )

    def test_login_com_email(self):
        resposta = self.client.post(
            reverse("login"),
            {"username": "mangger@empresa.com.br", "password": "SenhaForte123"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertRedirects(resposta, reverse("dashboard"))


class UsuariosSetoresFuncoesTests(TestCase):
    def dados_usuario_form(self, setor, funcao, email="novo@empresa.com.br"):
        return {
            "first_name": "Novo",
            "last_name": "Usuario",
            "email": email,
            "is_active": "on",
            "nivel_perfil": PerfilUsuario.NivelPerfil.USUARIO,
            "setor": setor,
            "funcao": funcao,
            "cargo": "",
            "receber_email_notificacao": "on",
            "papel_usuarios": "SEM_ACESSO",
            "papel_agenda": "VISUALIZADOR",
            "papel_rota_motoboy": "SEM_ACESSO",
            "papel_chamados_ti": "SEM_ACESSO",
            "papel_estoque_adm": "SEM_ACESSO",
            "papel_estoque_ti": "SEM_ACESSO",
            "papel_estoque_expediente": "SEM_ACESSO",
            "papel_avaliacao": "SEM_ACESSO",
            "enviar_convite": "",
        }

    def test_form_permite_funcoes_completas_para_setores_contabeis(self):
        form = UsuarioSistemaForm(
            self.dados_usuario_form(
                PerfilUsuario.Setor.CONTABIL,
                PerfilUsuario.Funcao.ESTAGIARIO,
            ),
            criacao=True,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_form_bloqueia_funcao_generica_em_setor_com_hierarquia_completa(self):
        form = UsuarioSistemaForm(
            self.dados_usuario_form(
                PerfilUsuario.Setor.FISCAL,
                PerfilUsuario.Funcao.ADMINISTRADOR,
            ),
            criacao=True,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("funcao", form.errors)

    def test_form_permite_funcoes_genericas_para_setores_menores(self):
        form = UsuarioSistemaForm(
            self.dados_usuario_form(
                PerfilUsuario.Setor.TI,
                PerfilUsuario.Funcao.ADMINISTRADOR,
            ),
            criacao=True,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_lista_usuarios_filtra_por_setor_e_funcao(self):
        admin = User.objects.create_user(
            username="admin.usuarios",
            email="admin.usuarios@empresa.com.br",
            password="Senha12345",
        )
        perfil_admin, _ = PerfilUsuario.objects.get_or_create(usuario=admin)
        perfil_admin.papel_usuarios = "ADMINISTRADOR"
        perfil_admin.setor = PerfilUsuario.Setor.TI
        perfil_admin.funcao = PerfilUsuario.Funcao.ADMINISTRADOR
        perfil_admin.save()

        contabil = User.objects.create_user(
            username="contabil",
            email="contabil@empresa.com.br",
            password="Senha12345",
            first_name="Carlos",
        )
        perfil_contabil, _ = PerfilUsuario.objects.get_or_create(usuario=contabil)
        perfil_contabil.setor = PerfilUsuario.Setor.CONTABIL
        perfil_contabil.funcao = PerfilUsuario.Funcao.ANALISTA
        perfil_contabil.save()

        fiscal = User.objects.create_user(
            username="fiscal",
            email="fiscal@empresa.com.br",
            password="Senha12345",
            first_name="Fernanda",
        )
        perfil_fiscal, _ = PerfilUsuario.objects.get_or_create(usuario=fiscal)
        perfil_fiscal.setor = PerfilUsuario.Setor.FISCAL
        perfil_fiscal.funcao = PerfilUsuario.Funcao.SUPERVISOR
        perfil_fiscal.save()

        self.client.login(username="admin.usuarios@empresa.com.br", password="Senha12345")
        resposta = self.client.get(
            reverse("usuarios_lista"),
            {
                "setor": PerfilUsuario.Setor.CONTABIL,
                "funcao": PerfilUsuario.Funcao.ANALISTA,
            },
        )

        self.assertContains(resposta, "contabil@empresa.com.br")
        self.assertNotContains(resposta, "fiscal@empresa.com.br")


class AgendaPermissaoTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome="Sala 1", capacidade=10)
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@empresa.com.br",
            password="Senha12345",
        )
        self.user = User.objects.create_user(
            username="ana",
            email="ana@empresa.com.br",
            password="Senha12345",
        )
        perfil = PerfilUsuario.objects.create(usuario=self.user)
        perfil.papel_agenda = "VISUALIZADOR"
        perfil.save()

        self.reuniao = Reuniao.objects.create(
            titulo="Planejamento",
            data=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(9, 0),
            hora_fim=time(10, 0),
            organizador="admin@empresa.com.br",
            organizador_usuario=self.admin,
            sala=self.sala,
        )

    def test_usuario_sem_ser_admin_da_agenda_nao_ve_reuniao_de_outro(self):
        self.client.login(username="ana@empresa.com.br", password="Senha12345")
        resposta = self.client.get(reverse("home"))
        self.assertContains(resposta, "Nenhuma reuniao encontrada")

    def test_admin_ve_reunioes_de_todos_usuarios_na_home(self):
        outro = User.objects.create_user(
            username="bruno",
            email="bruno@empresa.com.br",
            password="Senha12345",
        )
        Reuniao.objects.create(
            titulo="Reuniao privada",
            data=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(9, 0),
            hora_fim=time(10, 0),
            organizador=outro.email,
            organizador_usuario=outro,
            sala=self.sala,
        )

        self.client.login(username="admin@empresa.com.br", password="Senha12345")
        resposta = self.client.get(reverse("home"))
        self.assertEqual(resposta.context["total_reunioes"], 2)
        self.assertEqual(len(resposta.context["agenda_organizada"]), 1)
        self.assertContains(resposta, "Abrir calendario")

    def test_reuniao_vencida_e_concluida_continua_na_home(self):
        self.reuniao.organizador_usuario = self.user
        self.reuniao.organizador = self.user.email
        self.reuniao.data = timezone.localdate() - timedelta(days=1)
        self.reuniao.save()

        self.client.login(username="ana@empresa.com.br", password="Senha12345")
        resposta = self.client.get(reverse("home"))
        self.reuniao.refresh_from_db()

        self.assertEqual(self.reuniao.status, Reuniao.Status.REALIZADA)
        self.assertEqual(resposta.context["total_reunioes"], 1)
        self.assertNotContains(resposta, "Nenhuma reuniao encontrada")
        self.assertContains(resposta, "Abrir calendario")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="agenda@example.com",
    CALENDAR_INVITE_FROM_EMAIL="agenda@example.com",
    CALENDAR_REPLY_TO_EMAIL="agenda@example.com",
    CALENDAR_ORGANIZER_EMAIL="agenda@example.com",
    CALENDAR_ORGANIZER_NAME="Agenda Teste",
)
class AgendaFinalizacaoEmailTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome="Sala Teste", localizacao="Unidade teste", capacidade=8)
        self.usuario = User.objects.create_user(
            username="criador",
            email="criador@empresa.com.br",
            password="Senha12345",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=self.usuario)
        perfil.papel_agenda = "ADMINISTRADOR"
        perfil.save()

        self.reuniao = Reuniao.objects.create(
            titulo="Planejamento",
            descricao="Reuniao de planejamento",
            data=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(9, 0),
            hora_fim=time(10, 0),
            organizador=self.usuario.email,
            organizador_usuario=self.usuario,
            sala=self.sala,
            status=Reuniao.Status.AGENDADA,
        )
        self.client.login(username=self.usuario.email, password="Senha12345")

    def dados_formulario(self, status):
        return {
            "titulo": self.reuniao.titulo,
            "descricao": self.reuniao.descricao,
            "data": self.reuniao.data.isoformat(),
            "hora_inicio": "09:00",
            "hora_fim": "10:00",
            "sala": str(self.sala.pk),
            "status": status,
        }

    def test_envia_email_para_criador_ao_concluir_reuniao(self):
        resposta = self.client.post(
            reverse("editar_reuniao", args=[self.reuniao.pk]),
            self.dados_formulario(Reuniao.Status.REALIZADA),
        )

        self.assertRedirects(resposta, reverse("detalhe_reuniao", args=[self.reuniao.pk]))
        emails_finalizacao = [
            email for email in mail.outbox
            if email.subject == "Reunião finalizada: Planejamento"
        ]

        self.assertEqual(len(emails_finalizacao), 1)
        self.assertEqual(emails_finalizacao[0].to, ["criador@empresa.com.br"])
        self.assertIn("ATA de reuniões", emails_finalizacao[0].body)

    def test_nao_reenvia_email_de_finalizacao_se_ja_estava_concluida(self):
        self.reuniao.status = Reuniao.Status.REALIZADA
        self.reuniao.save(update_fields=["status"])

        self.client.post(
            reverse("editar_reuniao", args=[self.reuniao.pk]),
            self.dados_formulario(Reuniao.Status.REALIZADA),
        )

        emails_finalizacao = [
            email for email in mail.outbox
            if email.subject == "Reunião finalizada: Planejamento"
        ]
        self.assertEqual(emails_finalizacao, [])


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="agenda@example.com",
    CALENDAR_INVITE_FROM_EMAIL="agenda@example.com",
    CALENDAR_REPLY_TO_EMAIL="agenda@example.com",
    CALENDAR_ORGANIZER_EMAIL="agenda@example.com",
    CALENDAR_ORGANIZER_NAME="Agenda Teste",
)
class AgendaParticipantesFormTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(nome="Sala Teste", localizacao="Unidade teste", capacidade=8)
        self.usuario = User.objects.create_user(
            username="criadorparticipantes",
            email="criador.participantes@empresa.com.br",
            password="Senha12345",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=self.usuario)
        perfil.papel_agenda = "ADMINISTRADOR"
        perfil.save()

        self.participante = Participante.objects.create(
            nome="Junior",
            email="junior@falavinhacontabil.com.br",
        )
        self.client.login(username=self.usuario.email, password="Senha12345")

    def test_cria_reuniao_com_participante_selecionado(self):
        resposta = self.client.post(
            reverse("nova_reuniao"),
            {
                "titulo": "Alinhamento com Junior",
                "descricao": "Validacao do seletor de participantes",
                "data": (timezone.localdate() + timedelta(days=2)).isoformat(),
                "hora_inicio": "09:00",
                "hora_fim": "10:00",
                "sala": str(self.sala.pk),
                "status": Reuniao.Status.AGENDADA,
                "participantes": [str(self.participante.pk)],
            },
        )

        reuniao = Reuniao.objects.get(titulo="Alinhamento com Junior")
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(reuniao.participantes.filter(pk=self.participante.pk).exists())

    def test_cria_reuniao_com_novo_participante_sem_email(self):
        resposta = self.client.post(
            reverse("nova_reuniao"),
            {
                "titulo": "Alinhamento presencial",
                "descricao": "Participante sem e-mail cadastrado",
                "data": (timezone.localdate() + timedelta(days=2)).isoformat(),
                "hora_inicio": "10:00",
                "hora_fim": "11:00",
                "sala": str(self.sala.pk),
                "status": Reuniao.Status.AGENDADA,
                "novo_participante_nome": "Visitante sem email",
            },
        )

        reuniao = Reuniao.objects.get(titulo="Alinhamento presencial")
        participante = reuniao.participantes.get(nome="Visitante sem email")
        self.assertEqual(resposta.status_code, 302)
        self.assertIsNone(participante.email)


class AgendaCalendarioFiltroEmailTests(TestCase):
    def setUp(self):
        self.data_reuniao = timezone.localdate() + timedelta(days=10)
        self.sala = Sala.objects.create(nome="Sala Calendario", localizacao="Unidade teste", capacidade=8)
        self.admin = User.objects.create_user(
            username="admincalendario",
            email="admin.calendario@empresa.com.br",
            password="Senha12345",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=self.admin)
        perfil.papel_agenda = "ADMINISTRADOR"
        perfil.save()

        self.participante = Participante.objects.create(
            nome="Junior",
            email="junior@falavinhacontabil.com.br",
        )
        self.reuniao_participante = Reuniao.objects.create(
            titulo="Agenda Junior",
            descricao="Compromisso do participante",
            data=self.data_reuniao,
            hora_inicio=time(9, 0),
            hora_fim=time(10, 0),
            organizador="outra.pessoa@empresa.com.br",
            sala=self.sala,
        )
        self.reuniao_participante.participantes.add(self.participante)

        self.reuniao_organizador = Reuniao.objects.create(
            titulo="Organizacao Junior",
            descricao="Compromisso como organizador",
            data=self.data_reuniao,
            hora_inicio=time(10, 0),
            hora_fim=time(11, 0),
            organizador=self.participante.email,
            sala=self.sala,
        )
        self.reuniao_outro = Reuniao.objects.create(
            titulo="Agenda Outro Email",
            descricao="Nao deve aparecer no filtro",
            data=self.data_reuniao,
            hora_inicio=time(11, 0),
            hora_fim=time(12, 0),
            organizador="outro@empresa.com.br",
            sala=self.sala,
        )
        self.reuniao_cancelada = Reuniao.objects.create(
            titulo="Cancelada Junior",
            descricao="Nao deve aparecer na disponibilidade padrao",
            data=self.data_reuniao,
            hora_inicio=time(13, 0),
            hora_fim=time(14, 0),
            organizador="outra.pessoa@empresa.com.br",
            sala=self.sala,
            status=Reuniao.Status.CANCELADA,
        )
        self.reuniao_cancelada.participantes.add(self.participante)
        self.client.login(username=self.admin.email, password="Senha12345")

    def test_filtra_calendario_por_email_de_participante_e_organizador(self):
        resposta = self.client.get(
            reverse("lista_reunioes_mes", args=[self.data_reuniao.year, self.data_reuniao.month]),
            {"email": self.participante.email},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Agenda Junior")
        self.assertContains(resposta, "Organizacao Junior")
        self.assertNotContains(resposta, "Agenda Outro Email")
        self.assertNotContains(resposta, "Cancelada Junior")
        self.assertEqual(resposta.context["email_filtro"], self.participante.email)

    def test_selecionar_dia_exibe_apenas_reunioes_da_data(self):
        outro_dia = date(self.data_reuniao.year, self.data_reuniao.month, 1)
        if outro_dia == self.data_reuniao:
            outro_dia = date(self.data_reuniao.year, self.data_reuniao.month, 2)
        Reuniao.objects.create(
            titulo="Compromisso de outro dia",
            data=outro_dia,
            hora_inicio=time(8, 0),
            hora_fim=time(9, 0),
            organizador=self.admin.email,
            organizador_usuario=self.admin,
            sala=self.sala,
        )

        resposta = self.client.get(
            reverse("lista_reunioes_mes", args=[self.data_reuniao.year, self.data_reuniao.month]),
            {"dia": self.data_reuniao.isoformat()},
        )

        self.assertEqual(resposta.context["dia_selecionado"], self.data_reuniao)
        self.assertEqual(
            {reuniao.data for reuniao in resposta.context["reunioes_dia"]},
            {self.data_reuniao},
        )
        self.assertContains(resposta, "Agenda exclusiva do dia selecionado")


class EstoqueTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username="estoque",
            email="estoque@empresa.com.br",
            password="Senha12345",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=self.usuario)
        perfil.papel_estoque_ti = "ADMINISTRADOR"
        perfil.papel_estoque_expediente = "ADMINISTRADOR"
        perfil.save()
        self.item = ItemEstoque.objects.create(
            area=ItemEstoque.Area.TECNOLOGIA,
            nome="Mouse USB",
            estoque_minimo=2,
            custo_unitario=Decimal("6.00"),
        )

    def test_movimentacao_recalcula_saldo(self):
        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=10,
            responsavel=self.usuario,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_atual, 10)

        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
            quantidade=3,
            responsavel=self.usuario,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_atual, 7)

    def test_lista_consolida_entradas_saidas_e_saldo_por_produto(self):
        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=10,
            responsavel=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
            quantidade=4,
            quantidade_devolvida=1,
            responsavel=self.usuario,
        )

        self.client.login(username="estoque@empresa.com.br", password="Senha12345")
        resposta = self.client.get(reverse("estoque_ti"))
        item_lista = resposta.context["itens"].get(pk=self.item.pk)

        self.assertEqual(item_lista.total_entradas, 10)
        self.assertEqual(item_lista.total_saidas, 3)
        self.assertEqual(item_lista.quantidade_atual, 7)
        self.assertContains(resposta, "Estoque minimo")

    def test_edita_item_nome_valor_e_quantidade_atual(self):
        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=10,
            custo_unitario=Decimal("6.00"),
            responsavel=self.usuario,
        )

        self.client.login(username="estoque@empresa.com.br", password="Senha12345")
        resposta_lista = self.client.get(reverse("estoque_ti"))
        self.assertContains(resposta_lista, "Editar")

        resposta = self.client.post(
            reverse("editar_item_estoque", args=[self.item.pk]),
            {
                "categoria": ItemEstoque.Categoria.MOUSE,
                "codigo_proprio": "TI-001",
                "nome": "Mouse Sem Fio",
                "descricao": "Produto corrigido",
                "unidade_medida": "un",
                "custo_unitario": "12.50",
                "saldo_atual": "4",
                "estoque_minimo": "3",
                "ativo": "on",
            },
        )

        self.assertRedirects(resposta, reverse("detalhe_item_estoque", args=[self.item.pk]))
        self.item.refresh_from_db()
        self.assertEqual(self.item.nome, "Mouse Sem Fio")
        self.assertEqual(self.item.codigo_proprio, "TI-001")
        self.assertEqual(self.item.custo_unitario, Decimal("12.50"))
        self.assertEqual(self.item.quantidade_atual, 4)

        ajuste = MovimentacaoEstoque.objects.filter(
            item=self.item,
            observacao__icontains="Ajuste manual",
        ).latest("id")
        self.assertEqual(ajuste.tipo, MovimentacaoEstoque.TipoMovimento.SAIDA)
        self.assertEqual(ajuste.quantidade, 6)

    def test_administrador_exclui_item_de_estoque(self):
        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=10,
            responsavel=self.usuario,
        )

        self.client.login(username="estoque@empresa.com.br", password="Senha12345")
        resposta_lista = self.client.get(reverse("estoque_ti"))
        self.assertContains(resposta_lista, "Excluir")

        resposta_confirmacao = self.client.get(reverse("excluir_item_estoque", args=[self.item.pk]))
        self.assertContains(resposta_confirmacao, "Confirmar exclusao")

        resposta = self.client.post(reverse("excluir_item_estoque", args=[self.item.pk]))

        self.assertRedirects(resposta, reverse("estoque_ti"))
        self.assertFalse(ItemEstoque.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(MovimentacaoEstoque.objects.filter(item_id=self.item.pk).count(), 0)

    def test_supervisor_nao_ve_botao_excluir_item(self):
        supervisor = User.objects.create_user(
            username="supervisor.estoque",
            email="supervisor.estoque@empresa.com.br",
            password="Senha12345",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=supervisor)
        perfil.papel_estoque_ti = "SUPERVISOR"
        perfil.save()

        self.client.login(username=supervisor.email, password="Senha12345")
        resposta = self.client.get(reverse("estoque_ti"))

        self.assertContains(resposta, "Editar")
        self.assertNotContains(resposta, "Excluir")

    def test_relatorio_mensal_calcula_custo_retiradas_por_produto(self):
        MovimentacaoEstoque.objects.create(
            item=self.item,
            data_movimentacao=date(2026, 5, 1),
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=10,
            custo_unitario=Decimal("6.00"),
            responsavel=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            item=self.item,
            data_movimentacao=date(2026, 5, 10),
            tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
            quantidade=4,
            quantidade_devolvida=1,
            custo_unitario=Decimal("6.00"),
            setor="Fiscal",
            responsavel=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            item=self.item,
            data_movimentacao=date(2026, 6, 5),
            tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
            quantidade=2,
            custo_unitario=Decimal("6.00"),
            setor="Fiscal",
            responsavel=self.usuario,
        )

        self.client.login(username="estoque@empresa.com.br", password="Senha12345")
        resposta = self.client.get(
            reverse("relatorio_estoque", args=[ModuloSistema.ESTOQUE_TI.value]),
            {"periodo": "mes", "mes": "2026-05", "item": str(self.item.pk)},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["totais"]["custo_retiradas"], Decimal("18.00"))
        self.assertEqual(resposta.context["totais"]["retiradas"], 3)
        self.assertEqual(resposta.context["totais"]["entradas"], 10)
        self.assertEqual(len(resposta.context["relatorio"]["resumo_por_item"]), 1)
        self.assertEqual(
            resposta.context["relatorio"]["retiradas_por_data"][0]["data"],
            date(2026, 5, 10),
        )

    def test_relatorio_geral_sem_item_lista_todos_produtos(self):
        segundo_item = ItemEstoque.objects.create(
            area=ItemEstoque.Area.TECNOLOGIA,
            nome="Teclado USB",
            estoque_minimo=1,
            custo_unitario=Decimal("10.00"),
        )
        MovimentacaoEstoque.objects.create(
            item=self.item,
            data_movimentacao=date(2026, 5, 10),
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=1,
            custo_unitario=Decimal("6.00"),
            responsavel=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            item=segundo_item,
            data_movimentacao=date(2026, 5, 11),
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=2,
            custo_unitario=Decimal("10.00"),
            responsavel=self.usuario,
        )

        self.client.login(username="estoque@empresa.com.br", password="Senha12345")
        resposta = self.client.get(
            reverse("relatorio_estoque", args=[ModuloSistema.ESTOQUE_TI.value]),
            {"periodo": "mes", "mes": "2026-05"},
        )

        nomes = {
            linha["item"].nome
            for linha in resposta.context["relatorio"]["resumo_por_item"]
        }
        self.assertEqual(nomes, {"Mouse USB", "Teclado USB"})
        self.assertEqual(resposta.context["totais"]["itens_movimentados"], 2)

    def test_relatorio_por_datas_filtra_periodo_e_exporta_csv(self):
        MovimentacaoEstoque.objects.create(
            item=self.item,
            data_movimentacao=date(2026, 5, 1),
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=10,
            custo_unitario=Decimal("6.00"),
            responsavel=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            item=self.item,
            data_movimentacao=date(2026, 5, 10),
            tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
            quantidade=2,
            custo_unitario=Decimal("6.00"),
            setor="Fiscal",
            responsavel=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            item=self.item,
            data_movimentacao=date(2026, 5, 20),
            tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
            quantidade=1,
            custo_unitario=Decimal("6.00"),
            setor="Fiscal",
            responsavel=self.usuario,
        )

        self.client.login(username="estoque@empresa.com.br", password="Senha12345")
        filtros = {
            "periodo": "datas",
            "data_inicio": "2026-05-15",
            "data_fim": "2026-05-31",
            "tipo": MovimentacaoEstoque.TipoMovimento.SAIDA,
        }
        resposta = self.client.get(
            reverse("relatorio_estoque", args=[ModuloSistema.ESTOQUE_TI.value]),
            filtros,
        )
        self.assertEqual(resposta.context["totais"]["custo_retiradas"], Decimal("6.00"))
        self.assertEqual(resposta.context["totais"]["retiradas"], 1)

        resposta_csv = self.client.get(
            reverse("relatorio_estoque", args=[ModuloSistema.ESTOQUE_TI.value]),
            {**filtros, "export": "csv"},
        )
        self.assertEqual(resposta_csv.status_code, 200)
        self.assertEqual(resposta_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Mouse USB", resposta_csv.content.decode("utf-8-sig"))
        self.assertNotIn("10/05/2026", resposta_csv.content.decode("utf-8-sig"))

        resposta_pdf = self.client.get(
            reverse("relatorio_estoque", args=[ModuloSistema.ESTOQUE_TI.value]),
            {**filtros, "export": "pdf"},
        )
        self.assertEqual(resposta_pdf.status_code, 200)
        self.assertEqual(resposta_pdf["Content-Type"], "application/pdf")
        self.assertTrue(resposta_pdf.content.startswith(b"%PDF-1.4"))
        self.assertIn(".pdf", resposta_pdf["Content-Disposition"])

    def test_saida_com_devolucao_reduz_apenas_quantidade_liquida(self):
        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA,
            quantidade=10,
            responsavel=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            item=self.item,
            tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
            quantidade=5,
            quantidade_devolvida=2,
            setor="ADMINISTRATIVO",
            responsavel=self.usuario,
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_atual, 7)

    def test_estoque_expediente_inicia_vazio_e_permite_cadastrar_item(self):
        self.client.login(username="estoque@empresa.com.br", password="Senha12345")

        resposta_lista = self.client.get(reverse("estoque_expediente"))
        self.assertEqual(resposta_lista.status_code, 200)
        self.assertContains(resposta_lista, "Estoque Expediente")
        self.assertEqual(resposta_lista.context["itens"].count(), 0)

        resposta_cadastro = self.client.post(
            reverse("novo_item_estoque", args=[ModuloSistema.ESTOQUE_EXPEDIENTE.value]),
            {
                "categoria": ItemEstoque.Categoria.EXPEDIENTE,
                "codigo_proprio": "EXP-001",
                "nome": "Caneta Azul",
                "descricao": "",
                "unidade_medida": "un",
                "custo_unitario": "1.50",
                "estoque_minimo": "5",
                "ativo": "on",
            },
        )

        self.assertRedirects(resposta_cadastro, reverse("estoque_expediente"))
        item_expediente = ItemEstoque.objects.get(nome="Caneta Azul")
        self.assertEqual(item_expediente.area, ItemEstoque.Area.EXPEDIENTE)

    def test_categorias_estoque_podem_ser_criadas_editadas_e_excluidas(self):
        self.client.login(username="estoque@empresa.com.br", password="Senha12345")

        resposta_criacao = self.client.post(
            reverse("nova_categoria_estoque", args=[ModuloSistema.ESTOQUE_EXPEDIENTE.value]),
            {"nome": "Papelaria", "ativo": "on"},
        )
        self.assertRedirects(
            resposta_criacao,
            reverse("categorias_estoque", args=[ModuloSistema.ESTOQUE_EXPEDIENTE.value]),
        )
        categoria = CategoriaEstoque.objects.get(
            area=ItemEstoque.Area.EXPEDIENTE,
            codigo="PAPELARIA",
        )

        resposta_edicao = self.client.post(
            reverse("editar_categoria_estoque", args=[categoria.pk]),
            {"nome": "Papelaria Especial", "ativo": "on"},
        )
        self.assertRedirects(
            resposta_edicao,
            reverse("categorias_estoque", args=[ModuloSistema.ESTOQUE_EXPEDIENTE.value]),
        )
        categoria.refresh_from_db()
        self.assertEqual(categoria.nome, "Papelaria Especial")
        self.assertEqual(categoria.codigo, "PAPELARIA")

        resposta_exclusao = self.client.post(
            reverse("excluir_categoria_estoque", args=[categoria.pk])
        )
        self.assertRedirects(
            resposta_exclusao,
            reverse("categorias_estoque", args=[ModuloSistema.ESTOQUE_EXPEDIENTE.value]),
        )
        self.assertFalse(CategoriaEstoque.objects.filter(pk=categoria.pk).exists())

    def test_categoria_com_item_vinculado_nao_pode_ser_excluida(self):
        categoria = CategoriaEstoque.objects.create(
            area=ItemEstoque.Area.EXPEDIENTE,
            codigo="BLOCO",
            nome="Bloco",
        )
        ItemEstoque.objects.create(
            area=ItemEstoque.Area.EXPEDIENTE,
            categoria=categoria.codigo,
            nome="Bloco de notas",
            estoque_minimo=1,
        )

        self.client.login(username="estoque@empresa.com.br", password="Senha12345")
        resposta = self.client.post(reverse("excluir_categoria_estoque", args=[categoria.pk]))

        self.assertRedirects(
            resposta,
            reverse("categorias_estoque", args=[ModuloSistema.ESTOQUE_EXPEDIENTE.value]),
        )
        self.assertTrue(CategoriaEstoque.objects.filter(pk=categoria.pk).exists())


class RotaMotoboyTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username="rota",
            email="rota@empresa.com.br",
            password="Senha12345",
        )
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=self.usuario)
        perfil.papel_rota_motoboy = "ADMINISTRADOR"
        perfil.save()

    def dados_rota(self, paradas=None):
        paradas = paradas or [
            {
                "setor": "Fiscal",
                "empresa": "Empresa A",
                "tipo_servico": "COLETA",
                "endereco": "Rua Central, 100",
                "observacao": "",
            }
        ]
        dados = {
            "data": "2026-04-10",
            "horario_saida": "08:00",
            "endereco_inicio": "Av. Principal, 10",
            "paradas-TOTAL_FORMS": str(len(paradas)),
            "paradas-INITIAL_FORMS": "0",
            "paradas-MIN_NUM_FORMS": "1",
            "paradas-MAX_NUM_FORMS": "1000",
        }
        for indice, parada in enumerate(paradas):
            for campo, valor in parada.items():
                dados[f"paradas-{indice}-{campo}"] = valor
        return dados

    def test_criar_rota(self):
        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        with patch("sistema.modulos.rota_motoboy.views.otimizar_rota_motoboy") as otimizar:
            resposta = self.client.post(reverse("rota_motoboy_nova"), self.dados_rota())

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(RotaMotoboy.objects.count(), 1)
        rota = RotaMotoboy.objects.get()
        self.assertEqual(rota.endereco_inicio, "Av. Principal, 10")
        self.assertEqual(rota.endereco_destino, "")
        self.assertEqual(rota.titulo, "")
        self.assertEqual(rota.horario_saida.strftime("%H:%M"), "08:00")
        self.assertEqual(rota.paradas.count(), 1)
        self.assertEqual(rota.paradas.get().empresa, "Empresa A")
        self.assertTrue(
            EnderecoEmpresaMotoboy.objects.filter(
                nome="Empresa A",
                endereco="Rua Central, 100",
            ).exists()
        )
        otimizar.assert_called_once()

    def test_tela_nova_rota_permite_adicionar_rotas_antes_de_salvar(self):
        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        resposta = self.client.get(reverse("rota_motoboy_nova"))

        self.assertContains(resposta, "Horario de saida")
        self.assertNotContains(resposta, "Destino final")
        self.assertContains(resposta, "Adicionar parada")
        self.assertContains(resposta, "Salvar, organizar e calcular km")
        self.assertContains(resposta, 'name="paradas-TOTAL_FORMS"')

    def test_criar_rota_com_varias_paradas_antes_de_salvar(self):
        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        dados = self.dados_rota(
            [
                {
                    "setor": "Fiscal",
                    "empresa": "Empresa A",
                    "tipo_servico": "COLETA",
                    "endereco": "Rua A, 100",
                    "observacao": "",
                },
                {
                    "setor": "Contabil",
                    "empresa": "Empresa B",
                    "tipo_servico": "ENTREGA",
                    "endereco": "Rua B, 200",
                    "observacao": "Levar documentos",
                },
            ]
        )

        with patch("sistema.modulos.rota_motoboy.views.otimizar_rota_motoboy"):
            resposta = self.client.post(reverse("rota_motoboy_nova"), dados)

        rota = RotaMotoboy.objects.get()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(list(rota.paradas.order_by("ordem").values_list("empresa", flat=True)), ["Empresa A", "Empresa B"])

    def test_criar_rota_sem_horario_saida_e_sem_destino_final(self):
        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        dados = self.dados_rota()
        dados["horario_saida"] = ""

        with patch("sistema.modulos.rota_motoboy.views.otimizar_rota_motoboy"):
            resposta = self.client.post(reverse("rota_motoboy_nova"), dados)

        self.assertEqual(resposta.status_code, 302)
        rota = RotaMotoboy.objects.get()
        self.assertEqual(rota.endereco_destino, "")
        self.assertIsNone(rota.horario_saida)
        self.assertEqual(rota.paradas.count(), 1)

    def test_criar_rota_sem_local_de_partida(self):
        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        dados = self.dados_rota()
        dados["endereco_inicio"] = ""

        with patch("sistema.modulos.rota_motoboy.views.otimizar_rota_motoboy") as otimizar:
            resposta = self.client.post(reverse("rota_motoboy_nova"), dados)

        self.assertEqual(resposta.status_code, 302)
        rota = RotaMotoboy.objects.get()
        self.assertEqual(rota.endereco_inicio, "")
        self.assertEqual(rota.paradas.count(), 1)
        otimizar.assert_called_once()

    def test_criar_parada_por_endereco_avulso_sem_cliente(self):
        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        dados = self.dados_rota(
            [
                {
                    "setor": "",
                    "empresa": "",
                    "tipo_servico": "ENTREGA",
                    "endereco": "Rua Avulsa, 200",
                    "observacao": "",
                }
            ]
        )
        dados["endereco_inicio"] = ""

        with patch("sistema.modulos.rota_motoboy.views.otimizar_rota_motoboy"):
            resposta = self.client.post(reverse("rota_motoboy_nova"), dados)

        self.assertEqual(resposta.status_code, 302)
        parada = RotaMotoboy.objects.get().paradas.get()
        self.assertEqual(parada.empresa, "Endereco avulso")
        self.assertEqual(parada.endereco, "Rua Avulsa, 200")

    def test_editar_rota_altera_dados_e_paradas(self):
        rota = RotaMotoboy.objects.create(
            data=date(2026, 4, 10),
            titulo="Rota Fiscal",
            horario_saida=time(8, 0),
            endereco_inicio="Av. Principal, 10",
            endereco_destino="Av. Principal, 10",
        )
        rota.paradas.create(setor="Fiscal", empresa="Empresa A", tipo_servico="COLETA", endereco="Rua A, 100")

        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        with patch("sistema.modulos.rota_motoboy.views.otimizar_rota_motoboy"):
            resposta = self.client.post(
                reverse("rota_motoboy_editar", args=[rota.pk]),
                {
                    "data": "2026-04-10",
                    "horario_saida": "09:00",
                    "endereco_inicio": "Av. Atual, 99",
                    "paradas-TOTAL_FORMS": "1",
                    "paradas-INITIAL_FORMS": "0",
                    "paradas-MIN_NUM_FORMS": "1",
                    "paradas-MAX_NUM_FORMS": "1000",
                    "paradas-0-setor": "Fiscal",
                    "paradas-0-empresa": "Empresa B",
                    "paradas-0-tipo_servico": "ENTREGA",
                    "paradas-0-endereco": "Rua B, 200",
                    "paradas-0-observacao": "",
                },
            )

        rota.refresh_from_db()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(rota.titulo, "")
        self.assertEqual(rota.endereco_inicio, "Av. Atual, 99")
        self.assertEqual(rota.endereco_destino, "")
        self.assertEqual(rota.paradas.count(), 1)
        self.assertEqual(rota.paradas.get().empresa, "Empresa B")

    def test_busca_enderecos_da_rota_retorna_sugestoes(self):
        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        with patch(
            "sistema.modulos.rota_motoboy.views.buscar_sugestoes_endereco",
            return_value=[
                {
                    "nome": "Rua Central, Centro",
                    "latitude": "-23.0",
                    "longitude": "-46.0",
                }
            ],
        ):
            resposta = self.client.get(reverse("buscar_enderecos_rota"), {"q": "Rua Central"})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resultados"][0]["nome"], "Rua Central, Centro")

    def test_otimiza_rota_e_calcula_km(self):
        from sistema.modulos.rota_motoboy.roteirizacao import otimizar_rota_motoboy

        rota = RotaMotoboy.objects.create(
            data=date(2026, 4, 10),
            titulo="Rota Fiscal",
            endereco_inicio="Base",
            endereco_destino="Destino Final",
        )
        empresas = ["Empresa A", "Empresa B", "Empresa C", "Empresa D"]
        for ordem, empresa in enumerate(empresas, start=1):
            rota.paradas.create(
                ordem=ordem,
                setor="Fiscal",
                empresa=empresa,
                tipo_servico="COLETA",
                endereco=empresa,
            )

        coordenadas = {
            "Base": {"latitude": Decimal("0.000000"), "longitude": Decimal("0.000000")},
            "Empresa A": {"latitude": Decimal("0.010000"), "longitude": Decimal("0.010000")},
            "Empresa B": {"latitude": Decimal("0.020000"), "longitude": Decimal("0.020000")},
            "Empresa C": {"latitude": Decimal("0.030000"), "longitude": Decimal("0.030000")},
            "Empresa D": {"latitude": Decimal("0.040000"), "longitude": Decimal("0.040000")},
            "Destino Final": {"latitude": Decimal("0.050000"), "longitude": Decimal("0.050000")},
        }
        viagem = {
            "code": "Ok",
            "trips": [
                {
                    "distance": 10000,
                    "duration": 1800,
                    "legs": [
                        {"distance": 1000, "duration": 300},
                        {"distance": 2000, "duration": 300},
                        {"distance": 3000, "duration": 600},
                        {"distance": 4000, "duration": 600},
                        {"distance": 5000, "duration": 600},
                    ],
                }
            ],
            "waypoints": [
                {"waypoint_index": 0},
                {"waypoint_index": 1},
                {"waypoint_index": 3},
                {"waypoint_index": 2},
                {"waypoint_index": 4},
                {"waypoint_index": 5},
            ],
        }

        with patch(
            "sistema.modulos.rota_motoboy.roteirizacao.geocodificar_endereco",
            side_effect=lambda endereco: coordenadas[endereco],
        ), patch(
            "sistema.modulos.rota_motoboy.roteirizacao.obter_viagem_otimizada",
            return_value=viagem,
        ):
            otimizar_rota_motoboy(rota)

        rota.refresh_from_db()
        paradas = list(rota.paradas.order_by("ordem"))

        self.assertEqual([parada.empresa for parada in paradas], ["Empresa A", "Empresa C", "Empresa B", "Empresa D"])
        self.assertEqual([parada.distancia_km for parada in paradas], [
            Decimal("1.00"),
            Decimal("2.00"),
            Decimal("3.00"),
            Decimal("4.00"),
        ])
        self.assertEqual(rota.distancia_total_km, Decimal("10.00"))
        self.assertEqual(rota.duracao_total_minutos, 30)
        self.assertEqual(rota.latitude_destino, Decimal("0.050000"))
        self.assertEqual(rota.longitude_destino, Decimal("0.050000"))
        self.assertIsNotNone(rota.rota_otimizada_em)

    def test_otimiza_rota_sem_partida_usando_apenas_paradas(self):
        from sistema.modulos.rota_motoboy.roteirizacao import otimizar_rota_motoboy

        rota = RotaMotoboy.objects.create(
            data=date(2026, 4, 10),
            titulo="Rota sem partida",
            endereco_inicio="",
            endereco_destino="",
        )
        rota.paradas.create(ordem=1, empresa="Empresa A", tipo_servico="COLETA", endereco="Empresa A")
        rota.paradas.create(ordem=2, empresa="Empresa B", tipo_servico="ENTREGA", endereco="Empresa B")

        coordenadas = {
            "Empresa A": {"latitude": Decimal("0.010000"), "longitude": Decimal("0.010000")},
            "Empresa B": {"latitude": Decimal("0.020000"), "longitude": Decimal("0.020000")},
        }
        viagem = {
            "code": "Ok",
            "trips": [{"distance": 1500, "duration": 600, "legs": [{"distance": 1500, "duration": 600}]}],
            "waypoints": [{"waypoint_index": 0}, {"waypoint_index": 1}],
        }

        with patch(
            "sistema.modulos.rota_motoboy.roteirizacao.geocodificar_endereco",
            side_effect=lambda endereco: coordenadas[endereco],
        ), patch(
            "sistema.modulos.rota_motoboy.roteirizacao.obter_viagem_otimizada",
            return_value=viagem,
        ):
            otimizar_rota_motoboy(rota)

        rota.refresh_from_db()
        paradas = list(rota.paradas.order_by("ordem"))
        self.assertEqual(paradas[0].distancia_km, Decimal("0.00"))
        self.assertEqual(paradas[1].distancia_km, Decimal("1.50"))
        self.assertEqual(rota.distancia_total_km, Decimal("1.50"))
        self.assertIsNone(rota.latitude_inicio)
        self.assertIsNone(rota.longitude_inicio)

    def test_mes_exibe_historico_e_total_apenas_de_rotas_abertas(self):
        rota_aberta = RotaMotoboy.objects.create(
            data=date(2026, 4, 10),
            titulo="Aberta",
            status=RotaMotoboy.Status.ABERTA,
            distancia_total_km=Decimal("5.00"),
        )
        rota_aberta.paradas.create(ordem=1, empresa="Destino 1", endereco="Rua 1")
        rota_aberta.paradas.create(ordem=2, empresa="Destino 2", endereco="Rua 2")
        RotaMotoboy.objects.create(
            data=date(2026, 4, 11),
            titulo="Concluida",
            status=RotaMotoboy.Status.CONCLUIDA,
            distancia_total_km=Decimal("12.50"),
        )
        RotaMotoboy.objects.create(data=date(2026, 5, 10), titulo="Outro mes", status=RotaMotoboy.Status.ABERTA)

        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        resposta = self.client.get(reverse("rota_motoboy_mes", args=[2026, 4]))

        self.assertContains(resposta, "Rotas abertas no mes")
        self.assertContains(resposta, "<span>1</span>", html=True)
        self.assertEqual(resposta.context["km_total_mes"], Decimal("12.50"))
        self.assertContains(resposta, "Aberta")
        self.assertContains(resposta, "2 rotas")
        self.assertContains(resposta, "Concluida")
        self.assertNotContains(resposta, "Outro mes")

    def test_mes_exibe_paradas_em_lista_tabular_por_dia(self):
        rota = RotaMotoboy.objects.create(
            data=date(2026, 4, 17),
            titulo="Rota ADM",
            horario_saida=time(8, 0),
            endereco_inicio="Escritorio",
            endereco_destino="Escritorio",
        )
        rota.paradas.create(
            ordem=1,
            setor="ADM",
            empresa="Atacadao",
            tipo_servico="COLETA",
            endereco="Avenida Central, 100",
            observacao="Comprar materiais",
            status_final="OK",
        )

        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        resposta = self.client.get(reverse("rota_motoboy_mes", args=[2026, 4]))

        self.assertContains(resposta, "Atacadao")
        self.assertContains(resposta, "Status final")
        self.assertContains(resposta, "Comprar materiais")
        self.assertEqual(resposta.context["rotas_por_data"][0]["data"], date(2026, 4, 17))

    def test_marcar_rota_como_concluida_remove_da_lista_do_mes(self):
        rota = RotaMotoboy.objects.create(data=date(2026, 4, 10), titulo="Rota Fiscal")

        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        resposta = self.client.post(reverse("rota_motoboy_detalhe", args=[rota.pk]), {"acao_rota": "concluir"})
        rota.refresh_from_db()

        self.assertRedirects(resposta, reverse("rota_motoboy_mes", args=[2026, 4]))
        self.assertEqual(rota.status, RotaMotoboy.Status.CONCLUIDA)
        resposta_mes = self.client.get(reverse("rota_motoboy_mes", args=[2026, 4]))
        self.assertContains(resposta_mes, "<span>0</span>", html=True)
        self.assertContains(resposta_mes, "Rota de 10/04/2026")

    def test_marcar_rota_como_cancelada_remove_da_lista_do_mes(self):
        rota = RotaMotoboy.objects.create(data=date(2026, 4, 10), titulo="Rota Fiscal")

        self.client.login(username="rota@empresa.com.br", password="Senha12345")
        resposta = self.client.post(reverse("rota_motoboy_detalhe", args=[rota.pk]), {"acao_rota": "cancelar"})
        rota.refresh_from_db()

        self.assertRedirects(resposta, reverse("rota_motoboy_mes", args=[2026, 4]))
        self.assertEqual(rota.status, RotaMotoboy.Status.CANCELADA)
