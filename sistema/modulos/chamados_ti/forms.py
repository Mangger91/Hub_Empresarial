from django import forms

from sistema.models import ChamadoTI, ConfiguracaoChamadosTI


FORM_CONTROL = {"class": "form-control"}


class ChamadoTIAberturaForm(forms.ModelForm):
    colaborador = forms.CharField(
        label="Solicitante",
        required=False,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Quem solicitou"}),
    )

    class Meta:
        model = ChamadoTI
        fields = [
            "setor",
            "colaborador",
            "prioridade",
            "descricao",
            "anexo_imagem",
            "observacoes",
        ]
        widgets = {
            "setor": forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Ex.: Fiscal, RH, Recepção"}),
            "prioridade": forms.Select(attrs=FORM_CONTROL),
            "descricao": forms.Textarea(
                attrs={**FORM_CONTROL, "rows": 4, "placeholder": "Descreva a solicitação recebida"}
            ),
            "anexo_imagem": forms.FileInput(attrs={**FORM_CONTROL, "accept": "image/*"}),
            "observacoes": forms.Textarea(attrs={**FORM_CONTROL, "rows": 3}),
        }

    def clean_anexo_imagem(self):
        arquivo = self.cleaned_data.get("anexo_imagem")
        if not arquivo:
            return arquivo
        content_type = getattr(arquivo, "content_type", "")
        if content_type and not content_type.startswith("image/"):
            raise forms.ValidationError("Anexe apenas arquivos de imagem.")
        return arquivo


class ChamadoTIConclusaoForm(forms.ModelForm):
    class Meta:
        model = ChamadoTI
        fields = ["solucao"]
        widgets = {
            "solucao": forms.Textarea(
                attrs={
                    **FORM_CONTROL,
                    "rows": 5,
                    "placeholder": "Descreva a solução aplicada antes de finalizar o chamado",
                }
            ),
        }

    def clean_solucao(self):
        solucao = self.cleaned_data["solucao"].strip()
        if not solucao:
            raise forms.ValidationError("Informe a solução aplicada para concluir o chamado.")
        return solucao


class ConfiguracaoChamadosTIForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoChamadosTI
        fields = ["emails_notificacao_abertura"]
        labels = {
            "emails_notificacao_abertura": "Destinatários dos novos chamados",
        }
        widgets = {
            "emails_notificacao_abertura": forms.Textarea(
                attrs={
                    **FORM_CONTROL,
                    "rows": 5,
                    "placeholder": "junior@falavinhacontabil.com.br\nbruno.ares@falavinhacontabil.com.br",
                }
            ),
        }

    def clean_emails_notificacao_abertura(self):
        valor = self.cleaned_data["emails_notificacao_abertura"]
        emails = ConfiguracaoChamadosTI(emails_notificacao_abertura=valor).listar_emails_abertura()
        if not emails:
            raise forms.ValidationError("Informe ao menos um e-mail para receber os chamados.")
        for email in emails:
            forms.EmailField().clean(email)
        return "\n".join(emails)


class ImportarChamadosTIForm(forms.Form):
    substituir_chamados = forms.BooleanField(
        label="Limpar chamados atuais antes de importar",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox-control"}),
    )
    arquivo = forms.FileField(
        label="Planilha de chamados",
        widget=forms.FileInput(attrs={**FORM_CONTROL, "accept": ".xlsx,.xlsm"}),
    )
