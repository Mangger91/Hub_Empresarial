# WhatsApp Cloud API para reuniões

Esta integração usa exclusivamente a WhatsApp Cloud API oficial da Meta. A chamada sai do backend Django depois que uma nova reunião é confirmada no banco. Edição, cancelamento, reenvio e consultas GET não disparam WhatsApp.

Uma falha da Meta é registrada no log, com o telefone mascarado, e não desfaz a reunião nem interrompe o e-mail. Neste MVP o envio é síncrono; para um volume alto de participantes, o passo seguinte recomendado é usar uma fila de tarefas com worker persistente.

## 1. Obter os dados no painel da Meta

1. Acesse [Meta for Developers](https://developers.facebook.com/apps/) e crie ou abra um aplicativo do tipo Business.
2. Adicione o produto WhatsApp e abra `WhatsApp > API Setup`.
3. Copie o token temporário exibido em `Temporary access token`.
4. Copie o `Phone number ID` do número de teste.
5. Copie o `WhatsApp Business Account ID`. Ele não é necessário para enviar a mensagem, mas será usado para administrar templates e recursos da conta.
6. Confira a versão atual da Graph API mostrada no painel ou na [documentação oficial](https://developers.facebook.com/docs/whatsapp/cloud-api/). Informe exatamente essa versão, por exemplo `vXX.X`; o código não fixa uma versão para evitar usar uma versão obsoleta.

O token temporário é adequado somente para o teste inicial e expira. Em produção, gere um token de usuário do sistema com as permissões necessárias e mantenha-o apenas nas variáveis protegidas do ambiente.

## 2. Autorizar o destinatário de teste

Na mesma tela `WhatsApp > API Setup`, localize o campo `To`, escolha `Manage phone number list` e adicione seu número pessoal. A Meta enviará um código de confirmação para validar o destinatário.

O número de teste só envia para destinatários adicionados e verificados nessa lista. Cadastre no sistema o mesmo telefone, com DDD; `41999999999`, por exemplo, será convertido para `5541999999999`.

## 3. Configurar o ambiente

Adicione ao `.env` local ou às Environment Variables da hospedagem:

```env
DJANGO_WHATSAPP_CLOUD_API_ENABLED=True
DJANGO_WHATSAPP_CLOUD_API_BASE_URL=https://graph.facebook.com
DJANGO_WHATSAPP_CLOUD_API_VERSION=vXX.X
DJANGO_WHATSAPP_CLOUD_API_ACCESS_TOKEN=token_fornecido_pela_meta
DJANGO_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID=id_do_numero_de_teste
DJANGO_WHATSAPP_CLOUD_API_BUSINESS_ACCOUNT_ID=id_da_conta_whatsapp_business
DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_NAME=hello_world
DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_LANGUAGE=en_US
DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_FIELDS=
DJANGO_WHATSAPP_CLOUD_API_DEFAULT_COUNTRY_CODE=55
DJANGO_WHATSAPP_CLOUD_API_REQUEST_TIMEOUT=10
```

Não coloque o token no Git, GitHub, frontend ou arquivo de configuração versionado. Na Vercel, altere as variáveis do projeto e faça um novo deploy para a função receber os valores.

## 4. Fazer o primeiro envio

O template `hello_world` disponibilizado pela Meta não recebe parâmetros. Por isso, mantenha `DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_FIELDS` vazio no primeiro teste.

1. Reinicie o Django depois de alterar o `.env`.
2. Abra o cadastro de uma reunião.
3. Selecione ou crie um participante com o número autorizado no painel da Meta.
4. Salve a reunião.
5. Confirme o e-mail e a mensagem no telefone.

Uma resposta HTTP 2xx com um identificador `wamid...` confirma que a Cloud API aceitou a mensagem. O ID e o status HTTP são registrados no log; a entrega no aparelho também depende de o destinatário continuar autorizado e do template estar válido.

## 5. Criar o template de reunião

No WhatsApp Manager da conta, abra `Account tools > Message templates` e crie um template, por exemplo `aviso_reuniao`, com idioma `pt_BR`. Um corpo compatível com o sistema é:

```text
Olá, {{1}}!

Uma nova reunião foi agendada.

Data: {{2}}
Horário: {{3}}
Assunto: {{4}}
Local: {{5}}

Até lá!
```

Depois da aprovação, configure:

```env
DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_NAME=aviso_reuniao
DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_LANGUAGE=pt_BR
DJANGO_WHATSAPP_CLOUD_API_TEMPLATE_FIELDS=nome,data,horario,assunto,local
```

A ordem dos campos deve ser a mesma dos parâmetros `{{1}}` a `{{5}}`. Os campos aceitos atualmente são `nome`, `data`, `horario`, `assunto`, `local` e `descricao`.

## 6. API e webhook

O envio é feito com `POST /{versao}/{phone-number-id}/messages`, usando `messaging_product=whatsapp` e uma mensagem do tipo `template`, conforme a [referência oficial de mensagens](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/).

Um webhook não é necessário para o primeiro envio. Ele passa a ser necessário quando o sistema precisar receber eventos de entrega, leitura, falha posterior ou mensagens enviadas pelo usuário. Este MVP ainda não expõe uma URL de webhook.

Para validar a API agora:

1. Use primeiro o botão de envio de teste no painel da Meta.
2. Em seguida, crie a reunião no Django.
3. Procure no log por `HTTP 200` e pelo identificador `wamid...`.
4. Em caso de erro, confira o status HTTP e a mensagem devolvida pela Meta; o token nunca aparece no log.

Quando o webhook for implementado, configure em `WhatsApp > Configuration` uma URL HTTPS pública e um verify token próprio, assine o campo `messages` e valide os eventos seguindo a [documentação oficial de webhooks](https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/).

## 7. Arquivos envolvidos

- `sistema/integracoes/whatsapp.py`: normalização, cliente da Meta e processamento por participante.
- `sistema/modulos/agenda/services.py`: registra o envio com `transaction.on_commit`.
- `sistema/modulos/agenda/views.py`: criação transacional da reunião; não contém código HTTP.
- `sistema/modulos/agenda/forms.py`: valida e normaliza o telefone manual.
- `config/settings/base.py`: centraliza a configuração.
- `.env.example`: lista as variáveis sem credenciais.
- `sistema/test_whatsapp.py`: cobre normalização, criação, ausência de telefone, erro e vários participantes.

Não foi criada migration porque o campo opcional `Participante.whatsapp` já existia no banco.

## 8. Executar os testes

Somente a integração:

```powershell
python manage.py test sistema.test_whatsapp
```

Suíte completa:

```powershell
python manage.py test
```

Os testes usam mock e nunca chamam a API real da Meta.
