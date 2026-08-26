from datetime import date

from django import forms

from sistema.models import EnderecoEmpresaMotoboy, RotaMotoboy, RotaParada


FORM_CONTROL = {"class": "form-control"}


class RotaMotoboyForm(forms.ModelForm):
    class Meta:
        model = RotaMotoboy
        fields = [
            "data",
            "horario_saida",
            "endereco_inicio",
        ]
        labels = {
            "horario_saida": "Horario de saida",
            "endereco_inicio": "Local de partida",
        }
        widgets = {
            "data": forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
            "horario_saida": forms.TimeInput(attrs={**FORM_CONTROL, "type": "time"}),
            "endereco_inicio": forms.TextInput(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": "Ex.: rua, numero, cidade",
                    "autocomplete": "off",
                    "data-address-autocomplete": "true",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data"].required = False
        self.fields["horario_saida"].required = False
        self.fields["endereco_inicio"].required = False

    def clean_data(self):
        return self.cleaned_data.get("data") or date.today()


class RotaParadaForm(forms.ModelForm):
    class Meta:
        model = RotaParada
        fields = [
            "ordem",
            "setor",
            "empresa",
            "tipo_servico",
            "endereco",
            "observacao",
            "status_final",
        ]
        widgets = {
            "ordem": forms.NumberInput(attrs={**FORM_CONTROL, "min": "1"}),
            "setor": forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Ex.: Fiscal, RH"}),
            "empresa": forms.TextInput(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": "Nome da empresa",
                    "autocomplete": "off",
                    "data-company-autocomplete": "true",
                }
            ),
            "tipo_servico": forms.Select(attrs=FORM_CONTROL),
            "endereco": forms.TextInput(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": "Endereco para coleta/entrega",
                    "autocomplete": "off",
                    "data-address-autocomplete": "true",
                }
            ),
            "observacao": forms.Textarea(attrs={**FORM_CONTROL, "rows": 3}),
            "status_final": forms.Select(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["setor"].required = False
        self.fields["empresa"].required = False
        self.fields["tipo_servico"].required = False
        self.fields["endereco"].required = False
        self.fields["observacao"].required = False

    def clean(self):
        cleaned_data = super().clean()
        empresa = (cleaned_data.get("empresa") or "").strip()
        endereco = (cleaned_data.get("endereco") or "").strip()

        if not empresa and not endereco:
            raise forms.ValidationError(
                "Informe um cliente cadastrado ou digite um endereco avulso para a parada."
            )

        if not empresa and endereco:
            cleaned_data["empresa"] = "Endereco avulso"

        return cleaned_data


class RotaParadaCriacaoForm(RotaParadaForm):
    class Meta(RotaParadaForm.Meta):
        fields = [
            "setor",
            "empresa",
            "tipo_servico",
            "endereco",
            "observacao",
        ]


class EnderecoEmpresaMotoboyForm(forms.ModelForm):
    class Meta:
        model = EnderecoEmpresaMotoboy
        fields = ["nome", "endereco", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Nome da empresa"}),
            "endereco": forms.TextInput(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": "Endereco completo da empresa",
                    "autocomplete": "off",
                    "data-address-autocomplete": "true",
                }
            ),
            "ativo": forms.CheckboxInput(attrs={"class": "checkbox-control"}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if not nome:
            raise forms.ValidationError("Informe o nome da empresa.")

        enderecos = EnderecoEmpresaMotoboy.objects.filter(nome__iexact=nome)
        if self.instance and self.instance.pk:
            enderecos = enderecos.exclude(pk=self.instance.pk)
        if enderecos.exists():
            raise forms.ValidationError("Ja existe um endereco salvo para esta empresa.")
        return nome
