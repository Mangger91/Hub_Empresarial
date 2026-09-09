from django.urls import path

from .modulos.agenda import views as agenda_views
from .modulos.core import views as core_views
from .modulos.chamados_ti import views as chamados_ti_views
from .modulos.estoque import views as estoque_views
from .modulos.rota_motoboy import views as rota_motoboy_views
from .modulos.usuarios import views as usuarios_views


urlpatterns = [
    path("", core_views.inicio, name="inicio"),
    path("painel/", core_views.dashboard, name="dashboard"),
    path("usuarios/", usuarios_views.usuarios_lista, name="usuarios_lista"),
    path("usuarios/novo/", usuarios_views.usuario_novo, name="usuario_novo"),
    path("usuarios/<int:pk>/editar/", usuarios_views.usuario_editar, name="usuario_editar"),
    path("agenda/", agenda_views.home, name="home"),
    path("rota-motoboy/", rota_motoboy_views.rota_motoboy, name="rota_motoboy"),
    path("rota-motoboy/enderecos/", rota_motoboy_views.enderecos_empresas_rota, name="enderecos_empresas_rota"),
    path("rota-motoboy/enderecos/<int:pk>/editar/", rota_motoboy_views.editar_endereco_empresa_rota, name="editar_endereco_empresa_rota"),
    path("rota-motoboy/nova/", rota_motoboy_views.rota_motoboy_nova, name="rota_motoboy_nova"),
    path("rota-motoboy/buscar-enderecos/", rota_motoboy_views.buscar_enderecos_rota, name="buscar_enderecos_rota"),
    path("rota-motoboy/buscar-empresas/", rota_motoboy_views.buscar_empresas_rota, name="buscar_empresas_rota"),
    path("rota-motoboy/<int:pk>/editar/", rota_motoboy_views.rota_motoboy_editar, name="rota_motoboy_editar"),
    path("rota-motoboy/<int:pk>/", rota_motoboy_views.rota_motoboy_detalhe, name="rota_motoboy_detalhe"),
    path("rota-motoboy/<int:ano>/<int:mes>/", rota_motoboy_views.rota_motoboy_mes, name="rota_motoboy_mes"),
    path("agenda/nova/", agenda_views.nova_reuniao, name="nova_reuniao"),
    path("agenda/relatorio/", agenda_views.relatorio_reunioes, name="relatorio_reunioes"),
    path("agenda/<int:ano>/<int:mes>/", agenda_views.lista_reunioes_mes, name="lista_reunioes_mes"),
    path("reuniao/<int:pk>/", agenda_views.detalhe_reuniao, name="detalhe_reuniao"),
    path("reuniao/<int:pk>/editar/", agenda_views.editar_reuniao, name="editar_reuniao"),
    path("reuniao/<int:pk>/cancelar/", agenda_views.cancelar_reuniao, name="cancelar_reuniao"),
    path("reuniao/<int:pk>/reenviar-email/", agenda_views.reenviar_email_reuniao, name="reenviar_email_reuniao"),
    path("buscar-participantes/", agenda_views.buscar_participantes, name="buscar_participantes"),
    path("estoque/adm/", estoque_views.estoque_adm, name="estoque_adm"),
    path("estoque/ti/", estoque_views.estoque_ti, name="estoque_ti"),
    path("estoque/expediente/", estoque_views.estoque_expediente, name="estoque_expediente"),
    path("estoque/adm/importar/", estoque_views.importar_estoque_adm, name="importar_estoque_adm"),
    path("estoque/ti/importar/", estoque_views.importar_estoque_ti, name="importar_estoque_ti"),
    path("estoque/<str:modulo_codigo>/categorias/", estoque_views.categorias_estoque, name="categorias_estoque"),
    path("estoque/<str:modulo_codigo>/categorias/nova/", estoque_views.nova_categoria_estoque, name="nova_categoria_estoque"),
    path("estoque/categorias/<int:pk>/editar/", estoque_views.editar_categoria_estoque, name="editar_categoria_estoque"),
    path("estoque/categorias/<int:pk>/excluir/", estoque_views.excluir_categoria_estoque, name="excluir_categoria_estoque"),
    path("estoque/<str:modulo_codigo>/relatorio/", estoque_views.relatorio_estoque, name="relatorio_estoque"),
    path("estoque/<str:modulo_codigo>/novo/", estoque_views.novo_item_estoque, name="novo_item_estoque"),
    path("estoque/item/<int:pk>/", estoque_views.detalhe_item_estoque, name="detalhe_item_estoque"),
    path("estoque/item/<int:pk>/editar/", estoque_views.editar_item_estoque, name="editar_item_estoque"),
    path("estoque/item/<int:pk>/excluir/", estoque_views.excluir_item_estoque, name="excluir_item_estoque"),
    path("estoque/item/<int:pk>/movimentar/", estoque_views.movimentar_item_estoque, name="movimentar_item_estoque"),
    path("avaliacao-colaboradores/", core_views.avaliacao_colaboradores, name="avaliacao_colaboradores"),
    path("chamados-ti/", chamados_ti_views.chamados_ti, name="chamados_ti"),
    path("chamados-ti/novo/", chamados_ti_views.novo_chamado_ti, name="novo_chamado_ti"),
    path("chamados-ti/importar/", chamados_ti_views.importar_chamados_ti, name="importar_chamados_ti"),
    path(
        "chamados-ti/emails/",
        chamados_ti_views.configurar_emails_chamados_ti,
        name="configurar_emails_chamados_ti",
    ),
    path("chamados-ti/<int:pk>/editar/", chamados_ti_views.editar_chamado_ti, name="editar_chamado_ti"),
    path("chamados-ti/<int:pk>/assumir/", chamados_ti_views.assumir_chamado_ti, name="assumir_chamado_ti"),
    path("chamados-ti/<int:pk>/concluir/", chamados_ti_views.concluir_chamado_ti, name="concluir_chamado_ti"),
    path("minha-conta/", usuarios_views.minha_conta, name="minha_conta"),
    path("notificacoes/", core_views.central_notificacoes, name="central_notificacoes"),
    path("notificacoes/<int:pk>/", core_views.abrir_notificacao, name="abrir_notificacao"),
]
