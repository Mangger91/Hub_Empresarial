import calendar
from datetime import date, datetime

from django import forms
from django.utils.text import slugify

from sistema.models import CategoriaEstoque, ItemEstoque, ModuloSistema, MovimentacaoEstoque

from .regras import (
    area_do_modulo_estoque,
    categorias_estoque_por_area,
    categorias_estoque_por_modulo,
)


FORM_CONTROL = {"class": "form-control"}

SITUACOES_ESTOQUE_TI = (
    ("", "Nao se aplica"),
    ("uso", "Equipamento em uso"),
    ("estoque", "Equipamento em estoque"),
)


def descricao_sem_situacao_ti(descricao):
    linhas = str(descricao or "").splitlines()
    return "\n".join(
        linha for linha in linhas if not linha.strip().lower().startswith("situacao ti:")
    ).strip()


def situacao_ti_da_descricao(descricao):
    for linha in str(descricao or "").splitlines():
        if linha.strip().lower().startswith("situacao ti:"):
            valor = linha.split(":", 1)[1].strip().lower()
            if valor in {"uso", "em uso", "equipamento em uso"}:
                return "uso"
            if valor in {"estoque", "em estoque", "equipamento em estoque"}:
                return "estoque"
    return ""


class ItemEstoqueForm(forms.ModelForm):
    saldo_atual = forms.IntegerField(
        label="Quantidade atual",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={**FORM_CONTROL, "min": "0"}),
    )
    situacao_ti = forms.ChoiceField(
        label="Situacao no TI",
        choices=SITUACOES_ESTOQUE_TI,
        required=False,
        widget=forms.Select(attrs=FORM_CONTROL),
    )

    def __init__(self, *args, modulo=None, area=None, exibir_categoria=True, **kwargs):
        self.modulo_estoque = ModuloSistema(modulo) if modulo else None
        self.area_estoque = area
        super().__init__(*args, **kwargs)
        if self.modulo_estoque != ModuloSistema.ESTOQUE_TI and area != ItemEstoque.Area.TECNOLOGIA:
            self.fields.pop("situacao_ti", None)
        elif not self.is_bound:
            self.fields["situacao_ti"].initial = situacao_ti_da_descricao(
                self.instance.descricao if self.instance and self.instance.pk else ""
            )
        if not exibir_categoria:
            self.fields.pop("categoria", None)

        if not self.is_bound:
            self.fields["saldo_atual"].initial = (
                self.instance.quantidade_atual
                if self.instance and self.instance.pk
                else 0
            )
        ordem_campos = [
            "categoria",
            "codigo_proprio",
            "nome",
            "descricao",
            "situacao_ti",
            "unidade_medida",
            "custo_unitario",
            "saldo_atual",
            "estoque_minimo",
            "ativo",
        ]
        self.order_fields([campo for campo in ordem_campos if campo in self.fields])
        area_estoque = area
        categoria_atual = self.instance.categoria if self.instance and self.instance.pk else None
        if "categoria" not in self.fields:
            return
        if modulo:
            self.fields["categoria"].choices = categorias_estoque_por_modulo(
                self.modulo_estoque,
                incluir_codigo=categoria_atual,
            )
            return
        if not area_estoque and self.instance and self.instance.pk:
            area_estoque = self.instance.area
        if area_estoque:
            self.fields["categoria"].choices = categorias_estoque_por_area(
                area_estoque,
                incluir_codigo=categoria_atual,
            )

    def clean_saldo_atual(self):
        saldo_atual = self.cleaned_data.get("saldo_atual")
        if saldo_atual is not None:
            return saldo_atual
        if self.instance and self.instance.pk:
            return self.instance.quantidade_atual
        return 0

    def save(self, commit=True):
        item = super().save(commit=False)
        if "situacao_ti" in self.fields:
            descricao_base = descricao_sem_situacao_ti(item.descricao)
            situacao = self.cleaned_data.get("situacao_ti")
            if situacao:
                item.descricao = "\n".join(
                    parte for parte in [f"Situacao TI: {situacao}", descricao_base] if parte
                )
            else:
                item.descricao = descricao_base
        if commit:
            item.save()
            self.save_m2m()
        return item

    class Meta:
        model = ItemEstoque
        fields = [
            "categoria",
            "codigo_proprio",
            "nome",
            "descricao",
            "unidade_medida",
            "custo_unitario",
            "estoque_minimo",
            "ativo",
        ]
        widgets = {
            "categoria": forms.Select(attrs=FORM_CONTROL),
            "codigo_proprio": forms.TextInput(
                attrs={**FORM_CONTROL, "placeholder": "Ex.: AN01"}
            ),
            "nome": forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Nome do item"}),
            "descricao": forms.Textarea(attrs={**FORM_CONTROL, "rows": 4}),
            "unidade_medida": forms.TextInput(
                attrs={**FORM_CONTROL, "placeholder": "un, cx, kg..."}
            ),
            "custo_unitario": forms.NumberInput(
                attrs={**FORM_CONTROL, "step": "0.01", "min": "0"}
            ),
            "estoque_minimo": forms.NumberInput(attrs=FORM_CONTROL),
            "ativo": forms.CheckboxInput(attrs={"class": "checkbox-control"}),
        }


class CategoriaEstoqueForm(forms.ModelForm):
    def __init__(self, *args, area=None, **kwargs):
        self.area = area or getattr(kwargs.get("instance"), "area", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = CategoriaEstoque
        fields = ["nome", "ativo"]
        widgets = {
            "nome": forms.TextInput(
                attrs={**FORM_CONTROL, "placeholder": "Nome da categoria"}
            ),
            "ativo": forms.CheckboxInput(attrs={"class": "checkbox-control"}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if not nome:
            raise forms.ValidationError("Informe o nome da categoria.")

        categorias = CategoriaEstoque.objects.filter(area=self.area, nome__iexact=nome)
        if self.instance and self.instance.pk:
            categorias = categorias.exclude(pk=self.instance.pk)
        if categorias.exists():
            raise forms.ValidationError("Ja existe uma categoria com este nome neste estoque.")
        return nome

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk:
            return cleaned_data

        codigo = slugify(cleaned_data.get("nome") or "").upper().replace("-", "_")
        if not codigo:
            self.add_error("nome", "Informe um nome valido para gerar o codigo da categoria.")
            return cleaned_data

        if CategoriaEstoque.objects.filter(area=self.area, codigo=codigo).exists():
            self.add_error(
                "nome",
                "Ja existe uma categoria com nome semelhante neste estoque.",
            )
            return cleaned_data

        cleaned_data["codigo"] = codigo
        return cleaned_data

    def save(self, commit=True):
        categoria = super().save(commit=False)
        if not categoria.pk:
            categoria.area = self.area
            categoria.codigo = self.cleaned_data["codigo"]
        if commit:
            categoria.save()
        return categoria


class MovimentacaoEstoqueForm(forms.ModelForm):
    class Meta:
        model = MovimentacaoEstoque
        fields = [
            "data_movimentacao",
            "tipo",
            "quantidade",
            "quantidade_devolvida",
            "custo_unitario",
            "setor",
            "observacao",
        ]
        widgets = {
            "data_movimentacao": forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
            "tipo": forms.Select(attrs=FORM_CONTROL),
            "quantidade": forms.NumberInput(attrs=FORM_CONTROL),
            "quantidade_devolvida": forms.NumberInput(attrs={**FORM_CONTROL, "min": "0"}),
            "custo_unitario": forms.NumberInput(
                attrs={**FORM_CONTROL, "step": "0.01", "min": "0"}
            ),
            "setor": forms.TextInput(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": "Ex.: Administrativo, Fiscal, RH",
                }
            ),
            "observacao": forms.Textarea(
                attrs={
                    **FORM_CONTROL,
                    "rows": 3,
                    "placeholder": "Motivo da movimentacao, destinatario ou observacoes",
                }
            ),
        }


class RelatorioEstoqueFiltroForm(forms.Form):
    periodo = forms.ChoiceField(
        label="Periodo",
        choices=(("mes", "Mensal"), ("datas", "Por datas")),
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    mes = forms.CharField(
        label="Mes",
        required=False,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "type": "month"}),
    )
    data_inicio = forms.DateField(
        label="Data inicial",
        required=False,
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
    )
    data_fim = forms.DateField(
        label="Data final",
        required=False,
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
    )
    item = forms.ModelChoiceField(
        label="Produto",
        queryset=ItemEstoque.objects.none(),
        required=False,
        empty_label="Todos",
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    categoria = forms.ChoiceField(
        label="Categoria",
        required=False,
        choices=[("", "Todas")],
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    setor = forms.CharField(
        label="Setor",
        required=False,
        widget=forms.TextInput(
            attrs={**FORM_CONTROL, "placeholder": "Ex.: RH, Fiscal, Administrativo"}
        ),
    )
    tipo = forms.ChoiceField(
        label="Tipo",
        required=False,
        choices=[("", "Todos")] + list(MovimentacaoEstoque.TipoMovimento.choices),
        widget=forms.Select(attrs=FORM_CONTROL),
    )

    def __init__(self, *args, modulo=None, area=None, **kwargs):
        super().__init__(*args, **kwargs)
        area_estoque = area
        if modulo:
            area_estoque = area_do_modulo_estoque(ModuloSistema(modulo))

        if area_estoque:
            self.fields["item"].queryset = ItemEstoque.objects.filter(
                area=area_estoque,
                ativo=True,
            ).order_by("nome")
            self.fields["categoria"].choices = [
                ("", "Todas"),
                *categorias_estoque_por_area(area_estoque, incluir_inativas=True),
            ]

    def clean(self):
        cleaned_data = super().clean()
        periodo = cleaned_data.get("periodo") or "mes"

        if periodo == "datas":
            data_inicio = cleaned_data.get("data_inicio")
            data_fim = cleaned_data.get("data_fim")
            if not data_inicio:
                self.add_error("data_inicio", "Informe a data inicial.")
            if not data_fim:
                self.add_error("data_fim", "Informe a data final.")
            if data_inicio and data_fim and data_inicio > data_fim:
                self.add_error("data_fim", "A data final deve ser maior ou igual a inicial.")
        else:
            mes_referencia = cleaned_data.get("mes")
            if not mes_referencia:
                self.add_error("mes", "Informe o mes de referencia.")
            else:
                try:
                    data_mes = datetime.strptime(mes_referencia, "%Y-%m").date()
                except ValueError:
                    self.add_error("mes", "Informe um mes valido.")
                else:
                    ultimo_dia = calendar.monthrange(data_mes.year, data_mes.month)[1]
                    cleaned_data["data_inicio"] = date(data_mes.year, data_mes.month, 1)
                    cleaned_data["data_fim"] = date(data_mes.year, data_mes.month, ultimo_dia)

        if cleaned_data.get("setor"):
            cleaned_data["setor"] = cleaned_data["setor"].strip()

        return cleaned_data


class ImportarEstoquePlanilhasForm(forms.Form):
    substituir_estoque = forms.BooleanField(
        label="Limpar o Estoque ADM antes de importar",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "checkbox-control"}),
    )
    arquivo_copa = forms.FileField(
        label="Planilha de Copa",
        required=False,
        widget=forms.FileInput(attrs={**FORM_CONTROL, "accept": ".xlsx,.xlsm"}),
    )
    arquivo_expediente = forms.FileField(
        label="Planilha de Material de Expediente",
        required=False,
        widget=forms.FileInput(attrs={**FORM_CONTROL, "accept": ".xlsx,.xlsm"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        arquivos_enviados = [
            cleaned_data.get("arquivo_copa"),
            cleaned_data.get("arquivo_expediente"),
        ]
        total_arquivos = sum(1 for arquivo in arquivos_enviados if arquivo)
        if total_arquivos == 0:
            raise forms.ValidationError("Envie ao menos uma planilha para importar.")
        if total_arquivos > 1:
            raise forms.ValidationError(
                "Envie uma planilha por vez para evitar timeout no Vercel. "
                "Importe Copa limpando o estoque e depois Expediente sem limpar."
            )
        return cleaned_data


class ImportarEstoqueTIForm(forms.Form):
    tipo_equipamento = forms.ChoiceField(
        label="Tipo de equipamento",
        choices=[
            ("computador", "Computadores"),
            ("monitor", "Monitores"),
        ],
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    situacao = forms.ChoiceField(
        label="Destino da importacao",
        choices=[
            ("uso", "Equipamentos em uso"),
            ("estoque", "Equipamentos em estoque"),
        ],
        initial="uso",
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    substituir_itens = forms.BooleanField(
        label="Limpar itens desta categoria e situacao antes de importar",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox-control"}),
    )
    arquivo = forms.FileField(
        label="Arquivo Excel",
        widget=forms.FileInput(attrs={**FORM_CONTROL, "accept": ".xlsx,.xlsm"}),
    )
