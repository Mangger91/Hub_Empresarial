from django.db.models import Q

from sistema.models import CategoriaEstoque, ItemEstoque, ModuloSistema


MAPA_AREAS_ESTOQUE = {
    ModuloSistema.ESTOQUE_ADM: ItemEstoque.Area.ADMINISTRATIVO,
    ModuloSistema.ESTOQUE_TI: ItemEstoque.Area.TECNOLOGIA,
    ModuloSistema.ESTOQUE_EXPEDIENTE: ItemEstoque.Area.EXPEDIENTE,
}

CATEGORIAS_ESTOQUE_ADM = [
    (ItemEstoque.Categoria.GERAL, "Geral"),
    (ItemEstoque.Categoria.COPA, "Copa"),
    (ItemEstoque.Categoria.EXPEDIENTE, "Material de Expediente"),
]

CATEGORIAS_ESTOQUE_TI = [
    (ItemEstoque.Categoria.GERAL, "Geral"),
    (ItemEstoque.Categoria.ESCRITORIO_TI, "Escritorio TI"),
    (ItemEstoque.Categoria.COMPUTADOR, "Computador"),
    (ItemEstoque.Categoria.NOTEBOOK, "Notebook"),
    (ItemEstoque.Categoria.MONITOR, "Monitor"),
    (ItemEstoque.Categoria.TECLADO, "Teclado"),
    (ItemEstoque.Categoria.MOUSE, "Mouse"),
    (ItemEstoque.Categoria.HEADSET, "Headset"),
    (ItemEstoque.Categoria.IMPRESSORA, "Impressora"),
    (ItemEstoque.Categoria.REDE, "Rede e Internet"),
    (ItemEstoque.Categoria.TELEFONE, "Telefone"),
    (ItemEstoque.Categoria.ACESSORIO_TI, "Acessorios de TI"),
]

CATEGORIAS_ESTOQUE_EXPEDIENTE = [
    (ItemEstoque.Categoria.GERAL, "Geral"),
    (ItemEstoque.Categoria.EXPEDIENTE, "Material de Expediente"),
]

CATEGORIAS_POR_AREA = {
    ItemEstoque.Area.ADMINISTRATIVO: CATEGORIAS_ESTOQUE_ADM,
    ItemEstoque.Area.TECNOLOGIA: CATEGORIAS_ESTOQUE_TI,
    ItemEstoque.Area.EXPEDIENTE: CATEGORIAS_ESTOQUE_EXPEDIENTE,
}


def area_do_modulo_estoque(modulo):
    return MAPA_AREAS_ESTOQUE[modulo]


def rota_do_modulo_estoque(modulo):
    if modulo == ModuloSistema.ESTOQUE_ADM:
        return "estoque_adm"
    if modulo == ModuloSistema.ESTOQUE_EXPEDIENTE:
        return "estoque_expediente"
    return "estoque_ti"


def categorias_estoque_por_area(area, incluir_inativas=False, incluir_codigo=None):
    categorias = CategoriaEstoque.objects.filter(area=area)
    if not incluir_inativas:
        categorias = categorias.filter(Q(ativo=True) | Q(codigo=incluir_codigo))
    return list(categorias.order_by("nome").values_list("codigo", "nome"))


def categorias_estoque_por_modulo(modulo, incluir_inativas=False, incluir_codigo=None):
    return categorias_estoque_por_area(
        area_do_modulo_estoque(modulo),
        incluir_inativas=incluir_inativas,
        incluir_codigo=incluir_codigo,
    )


def valores_categorias_estoque_por_modulo(modulo):
    return {
        valor
        for valor, _label in categorias_estoque_por_modulo(
            modulo,
            incluir_inativas=True,
        )
    }
