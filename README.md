# Rodagem

Garagem pessoal para acompanhar a manutenção do carro por muitos anos: registre serviços e problemas em segundos pelo celular, planeje as próximas manutenções, receba alertas preventivos, acompanhe os gastos e leve ao mecânico um resumo organizado.

> O Rodagem organiza os seus registros com regras gerais e explicáveis. Ele não inventa intervalos de manutenção, não faz diagnósticos e não substitui a avaliação de um mecânico.

Antes de alterar regras, testes ou anexos, leia [docs/licoes-aprendidas.md](docs/licoes-aprendidas.md).

## Funcionalidades

### Garagem e quilometragem
- Conta local (sem credenciais padrão), vários veículos por proprietário e veículo ativo.
- A quilometragem atual é sempre a última leitura por data. Leituras retroativas coerentes são aceitas; retrocesso, data futura e duas leituras no mesmo dia são rejeitados.
- Serviço com data e km atualiza o histórico de km automaticamente.

### Serviços
- Botão **Registrar** (barra inferior no celular). Só a categoria é obrigatória; data em branco significa "não sei".
- Detalhes opcionais: tipo (preventiva, corretiva, inspeção), oficina, peças com marca/código, peças e mão de obra, garantia, fotos e PDFs.
- Valores como `89,90`, `1.234,56` ou `R$ 150`.

### Problemas e sintomas
- Sintoma em botões, descrição livre, local, gravidade percebida e acompanhamento até a resolução.
- Diagnóstico, **causas já descartadas** e solução ficam registrados para não repetir investigações. Um serviço pode resolver um problema.
- Atalho para registrar o caso já resolvido da água na porta traseira (não relacionado a combustível, bomba ou injeção).

### Plano de manutenção
- Itens com tipo — **recomendação do fabricante**, **preventiva pelo uso**, **inspeção sugerida** e **precisa de diagnóstico profissional** —, prioridade, motivo, fonte e custo estimado.
- Repetição por km e/ou meses (vale o que vier primeiro); a próxima referência sai do último serviço ligado ao item.
- 16 sugestões comuns **sem intervalos**: você informa os valores do manual. Itens do fabricante ficam "a validar" até a fonte ser informada e confirmada.

### Alertas
- Itens atrasados ou chegando, itens sem referência, programações vencidas, km desatualizado, problemas graves ou parados, sintomas recorrentes, garantias terminando e backup pendente.
- Cada alerta explica o motivo. Antecedência (km e dias) e prioridades exibidas são configuráveis.

### Assistente de manutenção
- **Descrever um sintoma**: possibilidades comuns (separando inspeção sugerida, possível problema que precisa de diagnóstico e o que costuma ser normal), urgência estimada com justificativa e perguntas para levar ao mecânico.
- Usa o histórico: relatos parecidos e suas soluções, **causas já descartadas** (não sugere de novo), serviços recentes em garantia, acessórios instalados e perfil de uso.
- **Revisão do carro**: manutenções recomendadas agora pelos quatro tipos, itens sem histórico confirmado, itens que dependem do tempo, sugestões pelo **perfil de uso** (trânsito, trajetos curtos, carro parado, carga, estradas ruins, poeira) e peças trocadas no último ano.
- **Resumo para o mecânico**: uma página pronta para imprimir ou salvar em PDF.
- Sinais de risco (freio, fumaça, cheiro de combustível, superaquecimento, luz vermelha, óleo) elevam a urgência e recomendam avaliação profissional.

### Linha do tempo e finanças
- Linha do tempo com serviços, peças, problemas, km e os próximos itens do plano, filtrável por tipo, categoria, situação e período.
- Gastos por período, categoria e tipo (preventiva x corretiva), média mensal, custo por km, total acumulado e previsão de 12 meses a partir do plano.

### Seus dados
- Planilhas CSV para Excel em português (com proteção contra injeção de fórmulas).
- Backup `.zip` com dados e anexos, restaurável pela interface em uma conta nova. Lembrete quando não há backup há 30 dias.

## Primeiros passos

1. Crie a conta e cadastre o carro (há um atalho para o Compacto).
2. Informe a quilometragem atual.
3. Em **Plano > Ver sugestões**, adicione os itens e preencha os intervalos do manual, indicando a fonte.
4. Registre os serviços antigos de que se lembrar (deixe a data em branco se não souber).
5. Em **Assistente > Perfil de uso**, marque como o carro é usado.
6. No dia a dia: **Registrar** para serviços, problemas e km; confira os alertas no sino.
7. Antes da oficina: **Assistente > Resumo para o mecânico**.
8. Uma vez por mês: **Mais opções > Seus dados > Baixar backup** e guarde o arquivo fora do computador.

### Backup agendado (opcional)

```powershell
.\.venv\Scripts\python.exe manage.py export_backup --username SEU_USUARIO --output D:\backups-rodagem
```

Pode ser agendado no Agendador de Tarefas do Windows. A pasta `backups/` (padrão) está fora do versionamento. Para restaurar: nova instalação, crie a conta e abra **Seus dados > Restaurar backup** antes de cadastrar veículos. A senha não faz parte do backup.

## Executar no Windows

Requer Python 3.13. Na pasta do projeto, usando PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abra http://127.0.0.1:8000 e crie sua conta no navegador. A criação da primeira conta só aceita conexões locais e fecha depois que existe um usuário; faça essa etapa antes de qualquer exposição externa.

Os atalhos do Compacto e do caso da porta apenas preenchem formulários; nada é salvo sem confirmação e nada é presumido (km, aquisição, combustível). Textos pessoais do atalho ficam em `.local/presets.json`, fora do versionamento. Campos aceitos: `brand`, `model`, `version`, `model_year`, `manufacture_year`, `engine`, `fuel`, `plate`, `notes`:

```json
{"exemplo": {"notes": "Descreva aqui trajetos e condições de uso."}}
```

Para uso local prolongado, após `collectstatic`, prefira o servidor WSGI instalado:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 config.wsgi:application
```

Pare com Ctrl+C. Não use `0.0.0.0` nem publique o servidor de desenvolvimento na internet. O layout é responsivo, mas o acesso pelo celular exige publicar a aplicação com HTTPS (veja "Limitações").

## Testar

```powershell
.\.venv\Scripts\python.exe manage.py test garage maintenance planning reports assistant
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Testes de navegador (opcionais, em banco temporário, sem tocar no banco pessoal):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
$env:RUN_BROWSER_TESTS = '1'
.\.venv\Scripts\python.exe manage.py test garage.test_browser -v 2
Remove-Item Env:RUN_BROWSER_TESTS
```

São cinco jornadas (conta e veículos; serviços e problemas no celular; plano e alertas; histórico, finanças, CSV, backup e restauração; assistente). Elas verificam erros de JavaScript, respostas HTTP de erro e rolagem horizontal entre 360 e 1500 px. Capturas ficam em `artifacts/`, fora do versionamento.

## Dados, backup e recuperação

- O banco fica em `db.sqlite3`, os anexos em `media/` e a chave local em `.local/secret.key`, todos fora do versionamento. Não há criptografia em repouso; proteja a conta do Windows.
- Backup recomendado: `.zip` de **Seus dados** ou `manage.py export_backup`. É testado automaticamente de ponta a ponta (exportar e restaurar em outra conta).
- Para migrar a instalação inteira, incluindo a conta: com o aplicativo parado, copie `db.sqlite3`, `media/` e `.local/`.
- CSV serve para consulta; não substitui o backup.
- Recuperar acesso (digite a senha no terminal, nunca no chat):

```powershell
.\.venv\Scripts\python.exe manage.py changepassword SEU_USUARIO
```

O bloqueio por falhas de login expira após 15 minutos. Todos os dados são privados por proprietário. Veículos não podem ser excluídos pela interface, para evitar perda de histórico.

## Arquitetura e decisões

Monólito modular Django 5.2 LTS, SQLite, templates, Bootstrap e HTMX, com recursos servidos localmente (sem CDN).

| App | Responsabilidade |
|---|---|
| `garage` | conta, veículos, quilometragem, painel |
| `maintenance` | serviços, peças, problemas, acompanhamento, anexos |
| `planning` | plano, sugestões, regras de vencimento (`rules.py`), alertas (`alerts.py`) |
| `reports` | linha do tempo, finanças, CSV, backup e restauração |
| `assistant` | base de conhecimento (`knowledge.py`), análise e revisão (`engine.py`), perfil de uso, resumo para o mecânico |

Decisões principais:

- **Django com templates e HTMX, sem SPA:** um único projeto fácil de manter, com autenticação, ORM, migrações e segurança maduros.
- **Uso local primeiro:** SQLite e servidor restrito ao computador. Na nuvem, o caminho é PostgreSQL, armazenamento privado de anexos, HTTPS e `DJANGO_DEBUG=0` com `DJANGO_SECRET_KEY` e `DJANGO_ALLOWED_HOSTS`, validando com `manage.py check --deploy`.
- **Dados derivados, não duplicados:** quilometragem atual, situação do plano, alertas e linha do tempo são calculados a cada requisição. Não há colunas ou tabelas que possam divergir.
- **Nenhum intervalo presumido:** sugestões vêm sem números (há testes que garantem isso), e recomendações do fabricante ficam "a validar" até terem fonte confirmada.
- **Assistente por regras, não IA generativa:** explicável, testável, gratuito, funciona offline e não "inventa" diagnósticos. A base é geral (não específica de um modelo) e sempre separa inspeção, possível problema e comportamento normal.
- **Segurança:** isolamento por proprietário em todas as consultas, CSRF, bloqueio de login, anexos validados pelo conteúdo e servidos só ao dono, CSV sem fórmulas e restauração de backup tratada como arquivo não confiável.
- **Privacidade no repositório público:** dados pessoais apenas em `.local/`; commits com e-mail noreply.

## Limitações conhecidas

- Alertas aparecem só dentro do aplicativo (sem e-mail ou notificação no celular).
- O acesso pelo celular exige publicar com HTTPS, por exemplo em uma hospedagem de baixo custo ou em um servidor doméstico com certificado; isso não foi configurado.
- Leituras de km manuais não podem ser editadas, e a troca de odômetro não é suportada.
- Metadados das fotos (como localização) não são removidos.
- A restauração de backup só funciona em conta sem veículos; mesclar dados não é suportado.
- A base do assistente é geral. Intervalos e particularidades do seu modelo dependem do manual e do mecânico.

## Manutenção do projeto

As dependências estão fixadas nas versões testadas; revise atualizações de segurança periodicamente (Django 5.2 LTS recebe correções até abril de 2028). Recursos de terceiros e licenças estão em `static/vendor`. A ilustração PNG é original e pode ser regenerada com `scripts/generate-artwork.ps1`.