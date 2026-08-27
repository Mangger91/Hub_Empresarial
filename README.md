Fluxo de desenvolvimento local validado em 30/07/2026.

# Agenda de Reuniões

Sistema interno de agendamento de reuniões desenvolvido com Django, com foco em organização visual, cadastro de participantes, controle por mês e envio de notificações.

## Destaques

- Interface com identidade visual profissional em tons de azul.
- Estrutura de `settings` separada por ambiente.
- Configuração sensível isolada em variáveis de ambiente.
- CSS centralizado em `static/css/app.css`.
- Fluxo de criação, edição, cancelamento e detalhe de reuniões.
- Envio de e-mail e integração opcional com a WhatsApp Cloud API oficial da Meta.

## WhatsApp Cloud API

A configuração do número de teste, templates e variáveis de ambiente está em
[docs/whatsapp-cloud-api.md](docs/whatsapp-cloud-api.md).

## Estrutura de configuração

O projeto usa os seguintes módulos:

- `config.settings.base`: configurações compartilhadas.
- `config.settings.dev`: ambiente local de desenvolvimento.
- `config.settings.prod`: ambiente de produção com endurecimento de segurança.

O ambiente ativo é controlado por `DJANGO_SETTINGS_MODULE`.

Exemplo para desenvolvimento:

```env
DJANGO_SETTINGS_MODULE=config.settings.dev
```

Exemplo para produção:

```env
DJANGO_SETTINGS_MODULE=config.settings.prod
```

## Como executar localmente

1. Crie e ative um ambiente virtual.
2. Instale as dependências:

```powershell
.\venv\Scripts\pip.exe install -r requirements.txt
```

3. Configure o arquivo `.env` com base no `.env.example`.
4. Aplique as migrações:

```powershell
.\venv\Scripts\python.exe manage.py migrate
```

5. Crie um superusuário se necessário:

```powershell
.\venv\Scripts\python.exe manage.py createsuperuser
```

6. Inicie o servidor:

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

## Arquivos importantes

- `config/settings/base.py`: base de configuração do Django.
- `config/settings/dev.py`: ajustes de desenvolvimento.
- `config/settings/prod.py`: ajustes de produção.
- `templates/base.html`: layout global.
- `static/css/app.css`: folha de estilos principal.
- `sistema/views.py`: fachada de compatibilidade para as views.
- `sistema/forms.py`: fachada de compatibilidade para os formularios.
- `sistema/modulos/`: organizacao real por modulo do sistema.

## Preparação para deploy

Antes de publicar em produção:

- Gere uma nova `DJANGO_SECRET_KEY`.
- Troque as credenciais de e-mail expostas anteriormente.
- Configure `DJANGO_ALLOWED_HOSTS` com o domínio real.
- Configure `DJANGO_CSRF_TRUSTED_ORIGINS` com a URL pública.
- Use `config.settings.prod` no ambiente de produção.
- Execute a coleta de arquivos estáticos:

```powershell
.\venv\Scripts\python.exe manage.py collectstatic --noinput
```

## Próximas melhorias sugeridas

- Adicionar testes automatizados para views e formulários.
- Criar logs de auditoria para criação, edição e cancelamento.
- Separar componentes de template em includes reutilizáveis.
- Adicionar paginação e busca avançada por reuniões.
