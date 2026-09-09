from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Case, F, IntegerField, Sum, Value, When
from django.utils import timezone


class PapelAcesso(models.TextChoices):
    SEM_ACESSO = "SEM_ACESSO", "Sem acesso"
    VISUALIZADOR = "VISUALIZADOR", "Visualizador"
    SUPERVISOR = "SUPERVISOR", "Supervisor"
    ADMINISTRADOR = "ADMINISTRADOR", "Administrador"


class ModuloSistema(models.TextChoices):
    AGENDA = "agenda", "Minha Agenda"
    USUARIOS = "usuarios", "Usuarios"
    ROTA_MOTOBOY = "rota_motoboy", "Rota do MotoBoy"
    ESTOQUE_ADM = "estoque_adm", "Estoque ADM"
    ESTOQUE_TI = "estoque_ti", "Estoque TI"
    ESTOQUE_EXPEDIENTE = "estoque_expediente", "Estoque Expediente"
    AVALIACAO = "avaliacao", "Avaliacao de Colaboradores"
    CHAMADOS_TI = "chamados_ti", "Chamados - TI"


class Sala(models.Model):
    nome = models.CharField(max_length=100)
    localizacao = models.CharField(max_length=150, blank=True, null=True)
    capacidade = models.PositiveIntegerField()
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome


class Participante(models.Model):
    nome = models.CharField(max_length=120)
    email = models.EmailField(unique=True, blank=True, null=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="participacoes_vinculadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nome} - {self.email}"


class PerfilUsuario(models.Model):
    class NivelPerfil(models.TextChoices):
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
        SUPERVISOR = "SUPERVISOR", "Supervisor"
        USUARIO = "USUARIO", "Usuario"

    class Setor(models.TextChoices):
        CONTABIL = "CONTABIL", "Contabil"
        FISCAL = "FISCAL", "Fiscal"
        PESSOAL = "PESSOAL", "Pessoal"
        EMPRESARIAL = "EMPRESARIAL", "Empresarial"
        COMERCIAL = "COMERCIAL", "Comercial"
        TI = "TI", "TI"
        RECEPCAO = "RECEPCAO", "Recepcao"
        FINANCEIRO = "FINANCEIRO", "Financeiro"

    class Funcao(models.TextChoices):
        ESTAGIARIO = "ESTAGIARIO", "Estagiario"
        ASSISTENTE = "ASSISTENTE", "Assistente"
        ANALISTA = "ANALISTA", "Analista"
        SUPERVISOR = "SUPERVISOR", "Supervisor"
        GERENTE = "GERENTE", "Gerente"
        DIRETOR = "DIRETOR", "Diretor"
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"

    SETORES_FUNCOES_COMPLETAS = {
        Setor.CONTABIL,
        Setor.FISCAL,
        Setor.PESSOAL,
        Setor.EMPRESARIAL,
    }
    FUNCOES_COMPLETAS = (
        Funcao.ESTAGIARIO,
        Funcao.ASSISTENTE,
        Funcao.ANALISTA,
        Funcao.SUPERVISOR,
        Funcao.GERENTE,
        Funcao.DIRETOR,
    )
    FUNCOES_ENXUTAS = (
        Funcao.ADMINISTRADOR,
        Funcao.SUPERVISOR,
        Funcao.ANALISTA,
    )

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil",
    )
    nivel_perfil = models.CharField(
        max_length=20,
        choices=NivelPerfil.choices,
        default=NivelPerfil.USUARIO,
    )
    cargo = models.CharField(max_length=120, blank=True)
    setor = models.CharField(
        max_length=20,
        choices=Setor.choices,
        blank=True,
        default="",
    )
    funcao = models.CharField(
        max_length=20,
        choices=Funcao.choices,
        blank=True,
        default="",
    )
    papel_usuarios = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.SEM_ACESSO,
    )
    papel_agenda = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.ADMINISTRADOR,
    )
    papel_rota_motoboy = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.SEM_ACESSO,
    )
    papel_estoque_adm = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.SEM_ACESSO,
    )
    papel_estoque_ti = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.SEM_ACESSO,
    )
    papel_estoque_expediente = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.SEM_ACESSO,
    )
    papel_avaliacao = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.SEM_ACESSO,
    )
    papel_chamados_ti = models.CharField(
        max_length=20,
        choices=PapelAcesso.choices,
        default=PapelAcesso.SEM_ACESSO,
    )
    receber_email_notificacao = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    CAMPOS_MODULO = {
        ModuloSistema.AGENDA: "papel_agenda",
        ModuloSistema.USUARIOS: "papel_usuarios",
        ModuloSistema.ROTA_MOTOBOY: "papel_rota_motoboy",
        ModuloSistema.ESTOQUE_ADM: "papel_estoque_adm",
        ModuloSistema.ESTOQUE_TI: "papel_estoque_ti",
        ModuloSistema.ESTOQUE_EXPEDIENTE: "papel_estoque_expediente",
        ModuloSistema.AVALIACAO: "papel_avaliacao",
        ModuloSistema.CHAMADOS_TI: "papel_chamados_ti",
    }

    def __str__(self):
        return f"Perfil de {self.usuario.get_full_name() or self.usuario.username}"

    @classmethod
    def funcoes_por_setor(cls, setor):
        if setor in cls.SETORES_FUNCOES_COMPLETAS:
            return cls.FUNCOES_COMPLETAS
        if setor in cls.Setor.values:
            return cls.FUNCOES_ENXUTAS
        return ()

    @classmethod
    def funcoes_choices_por_setor(cls, setor):
        valores_validos = cls.funcoes_por_setor(setor)
        return [
            (valor, cls.Funcao(valor).label)
            for valor in valores_validos
        ]

    @classmethod
    def funcoes_por_setor_para_json(cls):
        return {
            setor: [
                {"value": valor, "label": cls.Funcao(valor).label}
                for valor in cls.funcoes_por_setor(setor)
            ]
            for setor in cls.Setor.values
        }

    def clean(self):
        super().clean()
        if self.funcao and not self.setor:
            raise ValidationError({"setor": "Informe o setor antes de definir a funcao."})
        if self.setor and self.funcao and self.funcao not in self.funcoes_por_setor(self.setor):
            raise ValidationError(
                {"funcao": "A funcao selecionada nao pertence ao modelo deste setor."}
            )

    def papel_do_modulo(self, modulo):
        if self.usuario.is_superuser:
            return PapelAcesso.ADMINISTRADOR
        campo = self.CAMPOS_MODULO.get(modulo, "")
        return getattr(self, campo, PapelAcesso.SEM_ACESSO)

    def possui_acesso(self, modulo):
        return self.papel_do_modulo(modulo) != PapelAcesso.SEM_ACESSO

    def pode_editar(self, modulo):
        return self.papel_do_modulo(modulo) in {
            PapelAcesso.SUPERVISOR,
            PapelAcesso.ADMINISTRADOR,
        }

    def pode_excluir(self, modulo):
        return self.papel_do_modulo(modulo) == PapelAcesso.ADMINISTRADOR

    def eh_admin(self, modulo):
        return self.papel_do_modulo(modulo) == PapelAcesso.ADMINISTRADOR


class Reuniao(models.Model):
    SALAS_SEM_BLOQUEIO_DE_HORARIO = {"Externo", "Online"}

    class Status(models.TextChoices):
        AGENDADA = "AGENDADA", "Agendada"
        CANCELADA = "CANCELADA", "Cancelada"
        REALIZADA = "REALIZADA", "Concluida"

    titulo = models.CharField(max_length=150)
    descricao = models.TextField(blank=True, null=True)
    data = models.DateField()
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    organizador = models.CharField(max_length=120)
    organizador_usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reunioes_organizadas",
    )
    sala = models.ForeignKey(Sala, on_delete=models.PROTECT, related_name="reunioes")
    participantes = models.ManyToManyField(Participante, related_name="reunioes", blank=True)
    responsavel_ata = models.CharField(
        "Responsavel pela elaboracao e entrega da ata",
        max_length=150,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AGENDADA,
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.titulo} - {self.data.strftime('%d/%m/%Y')} as {self.hora_inicio.strftime('%H:%M')}"

    @property
    def nome_organizador(self):
        if self.organizador_usuario:
            return self.organizador_usuario.get_full_name() or self.organizador_usuario.email
        return self.organizador

    def clean(self):
        super().clean()

        if self.hora_inicio and self.hora_fim and self.hora_fim <= self.hora_inicio:
            raise ValidationError(
                {"hora_fim": "O horario de termino deve ser maior que o horario de inicio."}
            )

        if not self.sala_id or not self.data or not self.hora_inicio or not self.hora_fim:
            return

        if self.sala.nome in self.SALAS_SEM_BLOQUEIO_DE_HORARIO:
            return

        conflito = (
            self.__class__.objects.filter(
                sala=self.sala,
                data=self.data,
                status=self.Status.AGENDADA,
                hora_inicio__lt=self.hora_fim,
                hora_fim__gt=self.hora_inicio,
            )
            .exclude(pk=self.pk)
            .exists()
        )

        if conflito:
            raise ValidationError(
                {
                    "sala": (
                        "Ja existe uma reuniao agendada nesta sala para esse intervalo "
                        "de horario."
                    )
                }
            )


class ReuniaoLog(models.Model):
    class Acao(models.TextChoices):
        CRIACAO = "CRIACAO", "Criacao"
        EDICAO = "EDICAO", "Edicao"
        CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
        EXCLUSAO = "EXCLUSAO", "Exclusao"

    reuniao = models.ForeignKey(
        Reuniao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    reuniao_titulo = models.CharField(max_length=150)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs_reunioes",
    )
    acao = models.CharField(max_length=20, choices=Acao.choices)
    descricao = models.TextField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.acao} - {self.reuniao_titulo} - {self.criado_em}"


class Notificacao(models.Model):
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    modulo = models.CharField(max_length=30, choices=ModuloSistema.choices)
    titulo = models.CharField(max_length=180)
    mensagem = models.TextField()
    url_destino = models.CharField(max_length=255, blank=True)
    lida = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)
    lida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em"]

    def __str__(self):
        return f"{self.titulo} - {self.destinatario}"


class ChamadoTI(models.Model):
    class Prioridade(models.TextChoices):
        BAIXA = "BAIXA", "Baixa"
        MEDIA = "MEDIA", "Média"
        ALTA = "ALTA", "Alta"
        URGENTE = "URGENTE", "Urgente"

    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        AGUARDANDO = "AGUARDANDO", "Aguardando"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        CANCELADO = "CANCELADO", "Cancelado"

    codigo = models.CharField(max_length=20, unique=True, blank=True)
    data = models.DateField(default=timezone.localdate)
    atendente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chamados_ti_atendidos",
    )
    atendente_nome = models.CharField(max_length=120, blank=True)
    setor = models.CharField(max_length=80, blank=True)
    colaborador = models.CharField(max_length=120)
    prioridade = models.CharField(
        max_length=12,
        choices=Prioridade.choices,
        default=Prioridade.MEDIA,
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.ABERTO,
    )
    descricao = models.TextField("Descrição da solicitação")
    solucao = models.TextField("Solução aplicada", blank=True)
    anexo_imagem = models.FileField(upload_to="chamados_ti/", blank=True)
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fim = models.TimeField(null=True, blank=True)
    tempo_minutos = models.PositiveIntegerField(null=True, blank=True)
    aberto_em = models.DateTimeField(default=timezone.now)
    atendimento_iniciado_em = models.DateTimeField(null=True, blank=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    tempo_atendimento_minutos = models.PositiveIntegerField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chamados_ti_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"{self.codigo or self.pk} - {self.colaborador}"

    @property
    def tempo_horas(self):
        if self.tempo_minutos is None:
            return None
        return round(self.tempo_minutos / 60, 2)

    @property
    def tempo_atendimento_horas(self):
        if self.tempo_atendimento_minutos is None:
            return None
        return round(self.tempo_atendimento_minutos / 60, 2)

    def registrar_inicio_atendimento(self, usuario, quando=None):
        agora = quando or timezone.now()
        if not self.atendimento_iniciado_em:
            self.atendimento_iniciado_em = agora
        self.status = self.Status.EM_ANDAMENTO
        self.atendente = usuario
        self.atendente_nome = usuario.get_full_name() or usuario.email or usuario.username

    def registrar_conclusao(self, solucao, usuario, quando=None):
        agora = quando or timezone.now()
        if not self.atendimento_iniciado_em:
            self.registrar_inicio_atendimento(usuario, agora)
        elif not self.atendente:
            self.atendente = usuario
            if not self.atendente_nome:
                self.atendente_nome = usuario.get_full_name() or usuario.email or usuario.username
        self.status = self.Status.CONCLUIDO
        self.solucao = solucao
        self.concluido_em = agora
        duracao = self.concluido_em - self.atendimento_iniciado_em
        self.tempo_atendimento_minutos = max(0, int(duracao.total_seconds() // 60))


class ConfiguracaoChamadosTI(models.Model):
    emails_notificacao_abertura = models.TextField(
        default="junior@falavinhacontabil.com.br\nbruno.ares@falavinhacontabil.com.br",
        help_text="Informe um e-mail por linha, separados por virgula ou ponto e virgula.",
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuracoes_chamados_ti_atualizadas",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração de chamados TI"
        verbose_name_plural = "Configurações de chamados TI"

    def __str__(self):
        return "Configuração de chamados TI"

    @classmethod
    def carregar(cls):
        configuracao, _ = cls.objects.get_or_create(pk=1)
        return configuracao

    def listar_emails_abertura(self):
        texto = (self.emails_notificacao_abertura or "").replace(";", "\n").replace(",", "\n")
        return [email.strip() for email in texto.splitlines() if email.strip()]


class ItemEstoque(models.Model):
    class Area(models.TextChoices):
        ADMINISTRATIVO = "ADM", "Estoque ADM"
        TECNOLOGIA = "TI", "Estoque TI"
        EXPEDIENTE = "EXP", "Estoque Expediente"

    class Categoria(models.TextChoices):
        GERAL = "GERAL", "Geral"
        COPA = "COPA", "Copa"
        EXPEDIENTE = "EXPEDIENTE", "Material de Expediente"
        ESCRITORIO_TI = "ESCRITORIO_TI", "Escritorio TI"
        COMPUTADOR = "COMPUTADOR", "Computador"
        NOTEBOOK = "NOTEBOOK", "Notebook"
        MONITOR = "MONITOR", "Monitor"
        TECLADO = "TECLADO", "Teclado"
        MOUSE = "MOUSE", "Mouse"
        TELEFONE = "TELEFONE", "Telefone"
        HEADSET = "HEADSET", "Headset"
        IMPRESSORA = "IMPRESSORA", "Impressora"
        REDE = "REDE", "Rede e Internet"
        ACESSORIO_TI = "ACESSORIO_TI", "Acessorios de TI"

    area = models.CharField(max_length=3, choices=Area.choices)
    categoria = models.CharField(
        max_length=50,
        default=Categoria.GERAL,
    )
    codigo_proprio = models.CharField(max_length=30, blank=True)
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    unidade_medida = models.CharField(max_length=30, default="un")
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantidade_atual = models.IntegerField(default=0)
    estoque_minimo = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        unique_together = ("area", "nome")

    def __str__(self):
        return f"{self.get_area_display()} - {self.nome}"

    @property
    def categoria_nome(self):
        categoria = CategoriaEstoque.objects.filter(
            area=self.area,
            codigo=self.categoria,
        ).values_list("nome", flat=True).first()
        return categoria or self.categoria

    @property
    def estoque_baixo(self):
        return self.quantidade_atual <= 0 or (
            self.estoque_minimo > 0
            and self.quantidade_atual < self.estoque_minimo
        )

    @property
    def status_estoque(self):
        if self.quantidade_atual <= 0:
            return "Sem Estoque"
        if self.estoque_minimo > 0 and self.quantidade_atual < self.estoque_minimo:
            return "Em Atencao"
        return "Estoque Ok"

    def recalcular_quantidade(self):
        totais = self.movimentacoes.aggregate(
            saldo=Sum(
                Case(
                    When(tipo=MovimentacaoEstoque.TipoMovimento.ENTRADA, then=F("quantidade")),
                    When(
                        tipo=MovimentacaoEstoque.TipoMovimento.SAIDA,
                        then=Value(-1) * (F("quantidade") - F("quantidade_devolvida")),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
        )
        self.quantidade_atual = totais["saldo"] or 0
        self.save(update_fields=["quantidade_atual", "atualizado_em"])


class CategoriaEstoque(models.Model):
    area = models.CharField(max_length=3, choices=ItemEstoque.Area.choices)
    codigo = models.CharField(max_length=50)
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["area", "nome"]
        unique_together = (("area", "codigo"), ("area", "nome"))

    def __str__(self):
        return f"{self.get_area_display()} - {self.nome}"


class MovimentacaoEstoque(models.Model):
    class TipoMovimento(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saida"

    item = models.ForeignKey(
        ItemEstoque,
        on_delete=models.CASCADE,
        related_name="movimentacoes",
    )
    data_movimentacao = models.DateField(default=timezone.localdate)
    tipo = models.CharField(max_length=10, choices=TipoMovimento.choices)
    quantidade = models.PositiveIntegerField()
    quantidade_devolvida = models.PositiveIntegerField(default=0)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    setor = models.CharField(max_length=80, blank=True)
    observacao = models.TextField(blank=True)
    origem_externa = models.CharField(max_length=140, blank=True, null=True, unique=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimentacoes_estoque",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.item.nome} - {self.quantidade}"

    @property
    def quantidade_liquida(self):
        return self.quantidade - self.quantidade_devolvida

    @property
    def valor_total(self):
        return self.quantidade_liquida * self.custo_unitario

    def clean(self):
        super().clean()
        if self.quantidade <= 0:
            raise ValidationError({"quantidade": "Informe uma quantidade maior que zero."})

        if self.quantidade_devolvida > self.quantidade:
            raise ValidationError(
                {"quantidade_devolvida": "A quantidade devolvida nao pode ser maior do que a quantidade."}
            )

        if self.tipo == self.TipoMovimento.SAIDA and self.item_id:
            saldo_atual = self.item.quantidade_atual
            if self.pk:
                movimentacao_anterior = type(self).objects.get(pk=self.pk)
                if movimentacao_anterior.tipo == self.TipoMovimento.SAIDA:
                    saldo_atual += movimentacao_anterior.quantidade_liquida
                else:
                    saldo_atual -= movimentacao_anterior.quantidade

            if self.quantidade_liquida > saldo_atual:
                raise ValidationError(
                    {"quantidade": "A saida nao pode ser maior do que o saldo disponivel."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.item.recalcular_quantidade()

    def delete(self, *args, **kwargs):
        item = self.item
        with transaction.atomic():
            super().delete(*args, **kwargs)
            item.recalcular_quantidade()


class RotaMotoboy(models.Model):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        EM_ROTA = "EM_ROTA", "Em rota"
        CONCLUIDA = "CONCLUIDA", "Concluida"
        CANCELADA = "CANCELADA", "Cancelada"

    data = models.DateField()
    titulo = models.CharField(max_length=150, blank=True)
    horario_saida = models.TimeField(null=True, blank=True)
    endereco_inicio = models.CharField(max_length=255, blank=True)
    latitude_inicio = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude_inicio = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    endereco_destino = models.CharField(max_length=255, blank=True)
    latitude_destino = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude_destino = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    distancia_total_km = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    duracao_total_minutos = models.PositiveIntegerField(default=0)
    rota_otimizada_em = models.DateTimeField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.ABERTA,
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rotas_motoboy",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return self.titulo or f"Rota {self.data.strftime('%d/%m/%Y')}"


class EnderecoEmpresaMotoboy(models.Model):
    nome = models.CharField(max_length=140, unique=True)
    endereco = models.CharField(max_length=255)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} - {self.endereco}"


class RotaParada(models.Model):
    class TipoServico(models.TextChoices):
        COLETA = "COLETA", "Retirada"
        ENTREGA = "ENTREGA", "Entrega"
        OUTRO = "OUTRO", "Outro"

    class StatusFinal(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        OK = "OK", "OK"
        AMANHA = "AMANHA", "Amanha"
        CANCELADO = "CANCELADO", "Cancelado"

    rota = models.ForeignKey(
        RotaMotoboy,
        on_delete=models.CASCADE,
        related_name="paradas",
    )
    ordem = models.PositiveIntegerField(default=1)
    setor = models.CharField(max_length=80, blank=True)
    empresa = models.CharField(max_length=140, blank=True)
    horario_previsto = models.TimeField(null=True, blank=True)
    tipo_servico = models.CharField(
        max_length=10,
        choices=TipoServico.choices,
        default=TipoServico.COLETA,
    )
    endereco = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    distancia_km = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    duracao_minutos = models.PositiveIntegerField(default=0)
    observacao = models.TextField(blank=True)
    status_final = models.CharField(
        max_length=12,
        choices=StatusFinal.choices,
        default=StatusFinal.PENDENTE,
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "id"]

    def __str__(self):
        return f"{self.empresa} ({self.get_tipo_servico_display()})"
