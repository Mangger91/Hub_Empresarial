from django.db import migrations


def criar_categoria_telefone_ti(apps, schema_editor):
    CategoriaEstoque = apps.get_model("reunioes", "CategoriaEstoque")
    CategoriaEstoque.objects.get_or_create(
        area="TI",
        codigo="TELEFONE",
        defaults={"nome": "Telefone", "ativo": True},
    )


def remover_categoria_telefone_ti(apps, schema_editor):
    CategoriaEstoque = apps.get_model("reunioes", "CategoriaEstoque")
    CategoriaEstoque.objects.filter(area="TI", codigo="TELEFONE").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reunioes", "0024_reuniao_responsavel_ata"),
    ]

    operations = [
        migrations.RunPython(criar_categoria_telefone_ti, remover_categoria_telefone_ti),
    ]
