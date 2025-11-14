# CVAT Sync - POC/MVP

Sistema de sincronização de tasks do CVAT para gerenciamento local com Django.

## Características

- ✅ Sincronização manual de tasks do CVAT via comando Django
- ✅ **Webhook para sincronização automática em tempo real**
- ✅ Detecção automática de duplicatas (ignora tasks já sincronizadas)
- ✅ Interface web moderna com Tailwind CSS
- ✅ **Filtros compactos e expansíveis com estado persistente**
- ✅ **Filtros clicáveis nas colunas** (Projeto, Responsável, Status)
- ✅ Visualização detalhada de tasks e anotações
- ✅ Links diretos para tasks no CVAT
- ✅ **Sistema de auditoria completo de webhooks**
- ✅ **Validação HMAC SHA-256 para segurança de webhooks**
- ✅ Admin do Django para gerenciamento avançado
- ✅ Ordenação por data (mais recentes primeiro)

## Instalação

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Aplicar migrations

```bash
python manage.py migrate
```

### 3. Criar superusuário (opcional, para acessar o admin)

```bash
python manage.py createsuperuser
```

### 4. Configurar para produção (se for usar webhook)

Edite `config/settings.py`:

```python
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['seu-dominio.com', 'www.seu-dominio.com']

# CVAT Webhook Settings
CVAT_WEBHOOK_SECRET = "sua-chave-secreta-forte-aqui"
```

## Uso

### Sincronizar tasks do CVAT

Execute o comando de sincronização:

```bash
python manage.py sync_cvat
```

O comando irá:
1. Fazer login no CVAT
2. Buscar todos os jobs disponíveis
3. Verificar quais já existem no banco de dados
4. Criar apenas as novas tasks (ignorando duplicatas)
5. Exibir estatísticas de sincronização

#### Opções de filtro

Você pode filtrar a sincronização usando as seguintes opções:

```bash
# Filtrar por projeto
python manage.py sync_cvat --project-id 123

# Filtrar por task específica
python manage.py sync_cvat --task-id 456

# Filtrar por responsável
python manage.py sync_cvat --assignee "nome.usuario"

# Filtrar por status
python manage.py sync_cvat --status "completed"

# Forçar atualização de todas as tasks (ignora detecção de duplicatas)
python manage.py sync_cvat --force
```

### Iniciar servidor web

```bash
python manage.py runserver
```

Acesse:
- Interface principal: http://localhost:8000/
- Admin do Django: http://localhost:8000/admin/

## Funcionalidades da Interface

### Lista de Tasks

- **Cards de estatísticas**: Total de tasks e anotações totais
- **Filtros**: Busca por nome, filtro por projeto, responsável e status (compactos e expansíveis)
- **Filtros clicáveis**: Clique diretamente nas colunas de Projeto, Responsável ou Status para filtrar
- **Botão de sincronização**: Sincroniza diretamente pela interface
- **Visualização detalhada**: Todas as informações importantes em uma tabela
- **Ordenação**: Tasks mais recentes aparecem primeiro

### Detalhes da Task

- **Informações completas**: Nome, projeto, responsável, status, estado
- **Estatísticas de anotações**: Quantidade total de anotações
- **Link direto**: Botão para abrir a task diretamente no CVAT
- **Dados brutos**: Payload completo do CVAT para referência técnica

## Configuração de Webhook (Sincronização em Tempo Real)

O sistema suporta webhooks do CVAT para sincronização automática em tempo real quando jobs são criados ou atualizados.

### 1. Configurar o Secret Key

Edite `config/settings.py` e altere o valor de `CVAT_WEBHOOK_SECRET`:

```python
# CVAT Webhook Settings
CVAT_WEBHOOK_SECRET = "sua-chave-secreta-super-segura-aqui"
```

**Importante**: Use uma chave forte e única em produção. Você pode gerar uma com:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Configurar Webhook no CVAT

1. Acesse o admin do CVAT: `https://cvat.perplan.work/admin/`
2. Navegue para **Webhooks** ou **Webhooks Configuration**
3. Clique em **Add Webhook**
4. Configure os seguintes campos:

   - **URL**: `https://seu-servidor.com/cvat/webhook/`
   - **Description**: `Django Sync System`
   - **Events**: Selecione:
     - ✅ `create:job` - Quando um job é criado
     - ✅ `update:job` - Quando um job é atualizado
     - ✅ `delete:job` - Quando um job é deletado (remove do sistema)
   - **Content Type**: `application/json`
   - **Secret**: Cole o mesmo valor configurado em `CVAT_WEBHOOK_SECRET`
   - **Enable SSL Verification**: ✅ (recomendado em produção)
   - **Active**: ✅

5. Salve a configuração

### 3. Testar o Webhook

#### Teste Manual via curl:

```bash
curl -X POST https://seu-servidor.com/cvat/webhook/ \
  -H "Content-Type: application/json" \
  -H "X-Signature-256: sha256=$(echo -n '{"event":"create:job","job":{"id":123}}' | openssl dgst -sha256 -hmac 'sua-chave-secreta' | cut -d' ' -f2)" \
  -d '{"event":"create:job","job":{"id":123,"task_id":456,"task_name":"Test Task","status":"annotation"}}'
```

#### Verificar Logs:

1. Acesse o Django Admin: `http://localhost:8000/admin/`
2. Navegue para **Webhook Logs**
3. Verifique se os webhooks estão sendo recebidos e processados com sucesso

### 4. Monitoramento

Todos os webhooks recebidos são registrados no modelo `WebhookLog` com:
- **Event Type**: Tipo de evento (create:job, update:job, delete:job)
- **Status**: pending → processing → success/error
- **Payload**: Dados completos recebidos do CVAT
- **Source IP**: IP de origem da requisição
- **Error Message**: Mensagem de erro (se houver)
- **Timestamps**: Quando foi recebido e processado

### Segurança do Webhook

O endpoint implementa múltiplas camadas de segurança:

1. **Validação HMAC SHA-256**: Cada requisição deve conter um header `X-Signature-256` válido
2. **Content-Type Check**: Aceita apenas `application/json`
3. **IP Logging**: Registra o IP de origem de todas as requisições
4. **Error Handling**: Tratamento robusto de erros com logging completo
5. **CSRF Exempt**: O endpoint é acessível externamente (necessário para webhooks)

## Estrutura do Projeto

```
cvat_api/
├── config/                     # Configurações do Django
│   ├── settings.py
│   └── urls.py
├── cvat_sync/                  # App principal
│   ├── models.py              # Modelo CVATTask
│   ├── views.py               # Views da aplicação
│   ├── admin.py               # Admin customizado
│   ├── urls.py                # Rotas do app
│   └── management/
│       └── commands/
│           └── sync_cvat.py   # Comando de sincronização
├── template/                   # Templates HTML
│   ├── base.html
│   └── cvat_sync/
│       ├── task_list.html
│       └── task_detail.html
├── static/                     # Arquivos estáticos (CSS/JS)
├── manage.py
├── requirements.txt
└── README.md
```

## Modelo de Dados

### CVATTask

Campos principais:
- `cvat_job_id`: ID único do job no CVAT (chave primária)
- `cvat_task_id`: ID da task no CVAT
- `task_name`: Nome da task
- `project_id` / `project_name`: Informações do projeto
- `assignee`: Responsável pela task
- `status` / `state`: Status e estado da task no CVAT
- `manual_annotations`: Quantidade de anotações manuais
- `interpolated_annotations`: Quantidade de anotações interpoladas
- `total_annotations`: Total de anotações
- `cvat_url`: Link direto para o CVAT
- `cvat_data`: Dados completos em JSON
- `last_synced_at`: Data da última sincronização
- `created_at` / `updated_at`: Controle de timestamps

## Desenvolvimento Futuro

Possíveis melhorias para o MVP:

- [x] Webhook do CVAT para sincronização automática em tempo real ✅
- [x] Filtros compactos e clicáveis nas colunas ✅
- [x] Sistema de auditoria de webhooks (WebhookLog) ✅
- [ ] Dashboard com gráficos e métricas
- [ ] Sistema de notificações
- [ ] Exportação de relatórios (PDF, Excel)
- [ ] Filtros avançados e busca full-text
- [ ] API REST completa para integrações
- [ ] Sistema de permissões granular
- [ ] Histórico de mudanças

## Tecnologias Utilizadas

- **Backend**: Django 4.2
- **Database**: SQLite (pronto para migrar para PostgreSQL)
- **Frontend**: Tailwind CSS + FontAwesome
- **API Integration**: requests
- **CVAT**: API REST

## Licença

POC/MVP - Uso interno

## Suporte

Para questões ou problemas, entre em contato com a equipe de desenvolvimento.
