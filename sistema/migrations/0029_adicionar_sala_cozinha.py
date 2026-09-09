from django.db import migrations


def adicionar_sala_cozinha(apps, schema_editor):
    Sala = apps.get_model("reunioes", "Sala")
    sala = Sala.objects.filter(nome="Cozinha").first()

    if sala:
        campos = []
        if not sala.localizacao:
            sala.localizacao = "Copa"
            campos.append("localizacao")
        if not sala.capacidade:
            sala.capacidade = 8
            campos.append("capacidade")
        if not sala.ativa:
            sala.ativa = True
            campos.append("ativa")
        if campos:
            sala.save(update_fields=campos)
        return

    Sala.objects.create(
        nome="Cozinha",
        localizacao="Copa",
        capacidade=8,
        ativa=True,
    )


def manter_sala_cozinha_ao_reverter(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("reunioes", "0028_chamadoti_anexo_imagem_configuracaochamadosti"),
    ]

    operations = [
        migrations.RunPython(adicionar_sala_cozinha, manter_sala_cozinha_ao_reverter),
    ]
