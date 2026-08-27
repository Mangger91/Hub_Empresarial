from django import forms

from sistema.integracoes.whatsapp import normalizar_telefone_whatsapp
from sistema.models import Participante, Reuniao, Sala


FORM_CONTROL = {"class": "form-control"}


class ReuniaoForm(forms.ModelForm):
    novo_participante_nome = forms.CharField(
        required=False,
        label="Nome do participante",
        widget=forms.TextInput(
            attrs={
                **FORM_CONTROL,
                "placeholder": "Ex.: Joao da Silva",
            }
        ),
    )
    novo_participante_email = forms.EmailField(
        required=False,
        label="E-mail do participante (opcional)",
        widget=forms.EmailInput(
            attrs={
                **FORM_CONTROL,
                "placeholder": "Ex.: joao@empresa.com.br",
            }
        ),
    )
    novo_participante_whatsapp = forms.CharField(
        required=False,
        label="WhatsApp do participante (opcional)",
        widget=forms.TextInput(
            attrs={
                **FORM_CONTROL,
                "placeholder": "Ex.: 41999999999",
            }
        ),
        help_text="Informe DDD e numero. O codigo +55 e adicionado automaticamente.",
    )
    participantes = forms.ModelMultipleChoiceField(
        queryset=Participante.objects.none(),
        label="Participantes cadastrados",
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "participant-check"}),
    )

    class Meta:
        model = Reuniao
        fields = [
            "titulo",
            "descricao",
            "data",
            "hora_inicio",
            "hora_fim",
            "sala",
            "participantes",
            "responsavel_ata",
            "status",
        ]
        widgets = {
            "titulo": forms.TextInput(
                attrs={**FORM_CONTROL, "placeholder": "Digite o titulo da reuniao"}
            ),
            "descricao": forms.Textarea(
                attrs={
                    **FORM_CONTROL,
                    "rows": 4,
                    "placeholder": "Descreva objetivo, pauta e observacoes importantes",
                }
            ),
            "data": forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
            "hora_inicio": forms.TimeInput(attrs={**FORM_CONTROL, "type": "time"}),
            "hora_fim": forms.TimeInput(attrs={**FORM_CONTROL, "type": "time"}),
            "sala": forms.Select(attrs=FORM_CONTROL),
            "responsavel_ata": forms.TextInput(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": "Ex.: Lidiane",
                }
            ),
            "status": forms.Select(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["participantes"].queryset = Participante.objects.all().order_by("nome")
        self.fields["sala"].queryset = Sala.objects.filter(ativa=True).order_by("nome")
        self._campos_whatsapp_participantes = {}

        if self.is_bound:
            participantes_ids = self.data.getlist("participantes")
        elif self.instance and self.instance.pk:
            participantes_ids = self.instance.participantes.values_list("pk", flat=True)
        else:
            participantes_ids = []

        participantes = Participante.objects.filter(pk__in=participantes_ids)
        for participante in participantes:
            nome_campo = self.nome_campo_whatsapp_participante(participante.pk)
            self.fields[nome_campo] = forms.CharField(
                required=False,
                initial=participante.whatsapp,
            )
            self._campos_whatsapp_participantes[participante.pk] = nome_campo

    @staticmethod
    def nome_campo_whatsapp_participante(participante_id):
        return f"participante_whatsapp_{participante_id}"

    def clean(self):
        cleaned_data = super().clean()
        novo_nome = cleaned_data.get("novo_participante_nome")
        novo_email = cleaned_data.get("novo_participante_email")
        novo_whatsapp = cleaned_data.get("novo_participante_whatsapp")

        if (novo_email or novo_whatsapp) and not novo_nome:
            self.add_error("novo_participante_nome", "Informe o nome do novo participante.")

        whatsapp_invalido = False
        for nome_campo in self._campos_whatsapp_participantes.values():
            if self.is_bound and nome_campo not in self.data:
                continue
            numero = cleaned_data.get(nome_campo)
            if not numero:
                cleaned_data[nome_campo] = ""
                continue

            telefone = normalizar_telefone_whatsapp(numero)
            if not telefone:
                self.add_error(nome_campo, "Informe um WhatsApp valido com DDD.")
                whatsapp_invalido = True
                continue
            cleaned_data[nome_campo] = telefone

        if whatsapp_invalido:
            self.add_error("participantes", "Corrija o WhatsApp do participante selecionado.")

        return cleaned_data

    def clean_novo_participante_whatsapp(self):
        numero = self.cleaned_data.get("novo_participante_whatsapp")
        if not numero:
            return ""

        telefone = normalizar_telefone_whatsapp(numero)
        if not telefone:
            raise forms.ValidationError("Informe um WhatsApp valido com DDD.")
        return telefone


class RelatorioReuniaoFiltroForm(forms.Form):
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
    status = forms.ChoiceField(
        label="Status",
        required=False,
        choices=[("", "Todos")] + list(Reuniao.Status.choices),
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    pessoa = forms.CharField(
        label="Pessoa, nome ou e-mail",
        required=False,
        widget=forms.TextInput(
            attrs={**FORM_CONTROL, "placeholder": "Nome ou e-mail do participante/organizador"}
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get("data_inicio")
        data_fim = cleaned_data.get("data_fim")

        if not data_inicio:
            self.add_error("data_inicio", "Informe a data inicial.")
        if not data_fim:
            self.add_error("data_fim", "Informe a data final.")
        if data_inicio and data_fim and data_inicio > data_fim:
            self.add_error("data_fim", "A data final deve ser maior ou igual a inicial.")

        if cleaned_data.get("pessoa"):
            cleaned_data["pessoa"] = cleaned_data["pessoa"].strip()

        return cleaned_data
