from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reunioes", "0025_categoria_estoque_ti_telefone"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChamadoTI",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(blank=True, max_length=20, unique=True)),
                ("data", models.DateField(default=django.utils.timezone.localdate)),
                ("atendente_nome", models.CharField(blank=True, max_length=120)),
                ("setor", models.CharField(blank=True, max_length=80)),
                ("colaborador", models.CharField(max_length=120)),
                ("prioridade", models.CharField(choices=[("BAIXA", "Baixa"), ("MEDIA", "Media"), ("ALTA", "Alta"), ("URGENTE", "Urgente")], default="MEDIA", max_length=12)),
                ("status", models.CharField(choices=[("ABERTO", "Aberto"), ("EM_ANDAMENTO", "Em andamento"), ("AGUARDANDO", "Aguardando"), ("CONCLUIDO", "Concluido"), ("CANCELADO", "Cancelado")], default="ABERTO", max_length=15)),
                ("descricao", models.TextField(verbose_name="Descricao da solicitacao")),
                ("solucao", models.TextField(blank=True, verbose_name="Solucao aplicada")),
                ("hora_inicio", models.TimeField(blank=True, null=True)),
                ("hora_fim", models.TimeField(blank=True, null=True)),
                ("tempo_minutos", models.PositiveIntegerField(blank=True, null=True)),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("atendente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="chamados_ti_atendidos", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="chamados_ti_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-data", "-criado_em"],
            },
        ),
    ]
