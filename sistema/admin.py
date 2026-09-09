from django.contrib import admin, messages

from .models import (
    CategoriaEstoque,
    ChamadoTI,
    ConfiguracaoChamadosTI,
    EnderecoEmpresaMotoboy,
    ItemEstoque,
    MovimentacaoEstoque,
    Notificacao,
    Participante,
    PerfilUsuario,
    Reuniao,
    ReuniaoLog,
    RotaMotoboy,
    RotaParada,
    Sala,
)
from .utils import enviar_email_reuniao_finalizada


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ("nome", "localizacao", "capacidade", "ativa", "criada_em")
    search_fields = ("nome", "localizacao")
    list_filter = ("ativa",)


@admin.register(Participante)
class ParticipanteAdmin(admin.ModelAdmin):
    list_display = ("nome", "email", "whatsapp", "usuario", "criado_em")
    search_fields = ("nome", "email", "whatsapp", "usuario__username", "usuario__email")


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = (
        "usuario",
        "nivel_perfil",
        "setor",
        "funcao",
        "cargo",
        "papel_usuarios",
        "papel_agenda",
        "papel_rota_motoboy",
        "papel_estoque_adm",
        "papel_estoque_ti",
        "papel_estoque_expediente",
        "papel_avaliacao",
        "papel_chamados_ti",
        "receber_email_notificacao",
    )
    search_fields = ("usuario__username", "usuario__email", "usuario__first_name", "usuario__last_name")
    list_filter = (
        "nivel_perfil",
        "setor",
        "funcao",
        "papel_usuarios",
        "papel_agenda",
        "papel_rota_motoboy",
        "papel_estoque_adm",
        "papel_estoque_ti",
        "papel_estoque_expediente",
        "papel_avaliacao",
        "papel_chamados_ti",
        "receber_email_notificacao",
    )


@admin.register(ReuniaoLog)
class ReuniaoLogAdmin(admin.ModelAdmin):
    list_display = ("reuniao_titulo", "acao", "usuario", "criado_em")
    search_fields = ("reuniao_titulo", "usuario__username", "usuario__email", "descricao")
    list_filter = ("acao", "criado_em", "usuario")
    readonly_fields = ("reuniao", "reuniao_titulo", "usuario", "acao", "descricao", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Reuniao)
class ReuniaoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "data",
        "hora_inicio",
        "hora_fim",
        "sala",
        "organizador",
        "organizador_usuario",
        "status",
    )
    search_fields = ("titulo", "organizador", "organizador_usuario__username", "organizador_usuario__email")
    list_filter = ("status", "data", "sala")
    filter_horizontal = ("participantes",)

    def save_model(self, request, obj, form, change):
        status_anterior = None
        if change:
            status_anterior = Reuniao.objects.filter(pk=obj.pk).values_list("status", flat=True).first()

        super().save_model(request, obj, form, change)

        if status_anterior != Reuniao.Status.REALIZADA and obj.status == Reuniao.Status.REALIZADA:
            try:
                email_enviado = enviar_email_reuniao_finalizada(obj)
            except Exception as erro:
                self.message_user(
                    request,
                    f"Reuniao salva, mas houve erro ao enviar e-mail de finalizacao: {erro}",
                    level=messages.WARNING,
                )
            else:
                if not email_enviado:
                    self.message_user(
                        request,
                        "Reuniao salva, mas o criador nao possui e-mail cadastrado para receber o aviso da ATA.",
                        level=messages.WARNING,
                    )


class MovimentacaoEstoqueInline(admin.TabularInline):
    model = MovimentacaoEstoque
    extra = 0
    readonly_fields = ("responsavel", "criado_em")


@admin.register(CategoriaEstoque)
class CategoriaEstoqueAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "area", "ativo", "atualizada_em")
    search_fields = ("nome", "codigo")
    list_filter = ("area", "ativo")


@admin.register(ItemEstoque)
class ItemEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "codigo_proprio",
        "categoria_nome",
        "area",
        "quantidade_atual",
        "estoque_minimo",
        "custo_unitario",
        "ativo",
        "atualizado_em",
    )
    search_fields = ("nome", "codigo_proprio", "descricao")
    list_filter = ("area", "categoria", "ativo")
    inlines = [MovimentacaoEstoqueInline]


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "tipo",
        "data_movimentacao",
        "quantidade",
        "quantidade_devolvida",
        "custo_unitario",
        "setor",
        "responsavel",
        "criado_em",
    )
    search_fields = (
        "item__nome",
        "setor",
        "responsavel__username",
        "responsavel__email",
        "observacao",
    )
    list_filter = ("tipo", "item__area", "item__categoria", "setor", "data_movimentacao", "criado_em")


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "destinatario", "modulo", "lida", "criada_em")
    search_fields = ("titulo", "destinatario__username", "destinatario__email", "mensagem")
    list_filter = ("modulo", "lida", "criada_em")


@admin.register(ChamadoTI)
class ChamadoTIAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "colaborador",
        "setor",
        "prioridade",
        "status",
        "atendente_nome",
        "aberto_em",
        "atendimento_iniciado_em",
        "concluido_em",
        "tempo_atendimento_minutos",
    )
    search_fields = ("codigo", "colaborador", "setor", "descricao", "solucao", "observacoes")
    list_filter = ("status", "prioridade", "setor", "aberto_em")


@admin.register(ConfiguracaoChamadosTI)
class ConfiguracaoChamadosTIAdmin(admin.ModelAdmin):
    list_display = ("id", "atualizado_por", "atualizado_em")


class RotaParadaInline(admin.TabularInline):
    model = RotaParada
    extra = 0


@admin.register(RotaMotoboy)
class RotaMotoboyAdmin(admin.ModelAdmin):
    list_display = (
        "data",
        "horario_saida",
        "titulo",
        "status",
        "distancia_total_km",
        "responsavel",
        "criado_em",
    )
    search_fields = (
        "titulo",
        "endereco_inicio",
        "endereco_destino",
        "observacao",
        "responsavel__username",
        "responsavel__email",
    )
    list_filter = ("status", "data")
    inlines = [RotaParadaInline]


@admin.register(EnderecoEmpresaMotoboy)
class EnderecoEmpresaMotoboyAdmin(admin.ModelAdmin):
    list_display = ("nome", "endereco", "ativo", "atualizado_em")
    search_fields = ("nome", "endereco")
    list_filter = ("ativo",)


@admin.register(RotaParada)
class RotaParadaAdmin(admin.ModelAdmin):
    list_display = ("rota", "ordem", "setor", "empresa", "tipo_servico", "distancia_km", "status_final")
    search_fields = ("empresa", "setor", "endereco", "observacao")
    list_filter = ("tipo_servico", "status_final", "setor")
