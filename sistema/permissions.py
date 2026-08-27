from .models import ModuloSistema, PapelAcesso, PerfilUsuario


MODULOS_SISTEMA = [
    {
        "codigo": ModuloSistema.USUARIOS,
        "nome": "Usuarios",
        "icone": "users",
        "rota": "usuarios_lista",
        "descricao": "Cadastro de usuarios, niveis de perfil e permissoes individuais por modulo.",
    },
    {
        "codigo": ModuloSistema.AGENDA,
        "nome": "Minha Agenda",
        "icone": "calendar",
        "rota": "home",
        "descricao": "Reunioes integradas entre usuarios com notificacoes e controle por papel.",
    },
    {
        "codigo": ModuloSistema.ROTA_MOTOBOY,
        "nome": "Rota do MotoBoy",
        "icone": "route",
        "rota": "rota_motoboy",
        "descricao": "Planejamento de rotas com coletas e entregas por data.",
    },
    {
        "codigo": ModuloSistema.ESTOQUE_ADM,
        "nome": "Estoque ADM",
        "icone": "boxes",
        "rota": "estoque_adm",
        "descricao": "Controle administrativo com entradas, saidas e saldo em tempo real.",
    },
    {
        "codigo": ModuloSistema.ESTOQUE_TI,
        "nome": "Estoque TI",
        "icone": "monitor",
        "rota": "estoque_ti",
        "descricao": "Inventario tecnico para equipamentos, perifericos e reposicoes.",
    },
    {
        "codigo": ModuloSistema.ESTOQUE_EXPEDIENTE,
        "nome": "Estoque Expediente",
        "icone": "clipboard",
        "rota": "estoque_expediente",
        "descricao": "Controle de materiais de expediente com entradas, saidas e relatorios financeiros.",
    },
    {
        "codigo": ModuloSistema.AVALIACAO,
        "nome": "Avaliacao de Colaboradores",
        "icone": "chart",
        "rota": "avaliacao_colaboradores",
        "descricao": "Modulo inicial para centralizar ciclos, feedbacks e historico.",
    },
    {
        "codigo": ModuloSistema.CHAMADOS_TI,
        "nome": "Chamados - TI",
        "icone": "headphones",
        "rota": "chamados_ti",
        "descricao": "Fila de atendimento com espaco pronto para futura expansao.",
    },
]


def obter_perfil(usuario):
    if not usuario.is_authenticated:
        return None
    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=usuario)
    return perfil


def papel_do_usuario(usuario, modulo):
    perfil = obter_perfil(usuario)
    if not perfil:
        return PapelAcesso.SEM_ACESSO
    return perfil.papel_do_modulo(modulo)


def usuario_tem_acesso(usuario, modulo):
    return papel_do_usuario(usuario, modulo) != PapelAcesso.SEM_ACESSO


def usuario_pode_editar(usuario, modulo):
    return papel_do_usuario(usuario, modulo) in {
        PapelAcesso.SUPERVISOR,
        PapelAcesso.ADMINISTRADOR,
    }


def usuario_pode_excluir(usuario, modulo):
    return papel_do_usuario(usuario, modulo) == PapelAcesso.ADMINISTRADOR


def usuario_eh_admin(usuario, modulo):
    return papel_do_usuario(usuario, modulo) == PapelAcesso.ADMINISTRADOR


def montar_menu(usuario):
    menu = []
    for modulo in MODULOS_SISTEMA:
        papel = papel_do_usuario(usuario, modulo["codigo"]) if usuario.is_authenticated else PapelAcesso.SEM_ACESSO
        menu.append(
            {
                **modulo,
                "papel": papel,
                "papel_label": PapelAcesso(papel).label if papel in PapelAcesso.values else papel,
                "possui_acesso": papel != PapelAcesso.SEM_ACESSO,
            }
        )
    return menu
