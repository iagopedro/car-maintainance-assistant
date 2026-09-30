# Fluxos de interface

Roteiro de validação visual, executado no navegador integrado do VS Code, um fluxo por vez. Complementa os testes automatizados (`garage/test_browser.py`): aqui o objetivo é acompanhar a experiência real, passo a passo.

## Ambiente

Os fluxos rodam em uma instância isolada, com banco, anexos e cookies próprios em `.local/flows/` (fora do versionamento). O banco pessoal (`db.sqlite3`) não é tocado.

```powershell
.\scripts\flow-server.ps1 -Reset   # começa do zero (apaga só .local/flows)
.\scripts\flow-server.ps1          # continua com os dados dos fluxos anteriores
```

Endereço: http://127.0.0.1:8001. Os fluxos são sequenciais: cada um usa os dados criados pelos anteriores. Conta de teste: `fluxo-teste`, senha atual `Estrada-Azul-2027!` (fictícia, só para esta instância).

## Situação

| # | Fluxo | Situação | Data |
|---|---|---|---|
| 1 | Primeiro acesso e conta | Aprovado | 30/09/2026 |
| 2 | Garagem e quilometragem | Aprovado | 30/09/2026 |
| 3 | Serviços | Aprovado | 30/09/2026 |
| 4 | Problemas | Pendente | |
| 5 | Plano de manutenção | Pendente | |
| 6 | Alertas e preferências | Pendente | |
| 7 | Linha do tempo e finanças | Pendente | |
| 8 | Assistente de manutenção | Pendente | |
| 9 | Seus dados: CSV, backup e restauração | Pendente | |
| 10 | Celular, teclado e acessibilidade | Pendente | |

## 1. Primeiro acesso e conta

Pré-condição: instância zerada (`-Reset`).

| Passo | Ação | Resultado esperado |
|---|---|---|
| 1.1 | Abrir a instância | Redireciona para "Criar sua conta"; não há credenciais padrão |
| 1.2 | Criar conta com senha fraca (`12345678`) | Conta não criada; erros de validação da senha visíveis |
| 1.3 | Criar a conta `fluxo-teste` com senha forte | Painel "Visão geral" com boas-vindas e botão "Cadastrar veículo" |
| 1.4 | Sair | Volta para "Entrar na conta" |
| 1.5 | Entrar com senha errada | Mensagem de erro; continua deslogado |
| 1.6 | Entrar com a senha correta | Painel |
| 1.7 | Mais opções > Alterar senha > nova senha | "Senha atualizada" |
| 1.8 | Sair e entrar com a nova senha | Painel |
| 1.9 | Errar 5 vezes o login do usuário `intruso` | Página "Acesso temporariamente limitado" (bloqueio de 15 min só para esse usuário) |

Achados:

- A senha `Fluxo-teste-2026!` foi recusada por ser parecida com o usuário. Comportamento correto; senhas usadas: `Garagem-Verde-2026!` e, depois da troca, `Estrada-Azul-2027!`.
- Corrigido: o nome acessível dos campos obrigatórios saía colado ("Usuárioobrigatório"). O asterisco ficou oculto para leitores de tela e o rótulo ganhou " (obrigatório)" visível só para eles.

## 2. Garagem e quilometragem

| Passo | Ação | Resultado esperado |
|---|---|---|
| 2.1 | Painel > "Cadastrar veículo" | Formulário em branco, sem dados pré-preenchidos; "Conferida na documentação" desmarcado |
| 2.2 | Cadastrar "Exemplo Compacto 2020" com 45.000 km | Página do veículo com 45.000 km |
| 2.3 | Editar: versão "Básica" | Dado salvo |
| 2.4 | Registrar km: 44.000 com data de 30 dias atrás (origem: documento) | Aceita (retroativa coerente); atual continua 45.000 |
| 2.5 | Registrar km: 46.000 com data de 15 dias atrás | Rejeitado: maior que a leitura posterior |
| 2.6 | Histórico de km: filtrar origem "Documento" | Só a leitura de 44.000 |
| 2.7 | Cadastrar "Exemplo Sedã 2015" (120.000 km) e trocar o veículo ativo | Painel troca de carro; dados separados |
| 2.8 | Voltar o veículo ativo para o Exemplo Compacto | Painel do Exemplo Compacto |

Achados (todos corrigidos):

- O seletor de veículo ativo trocava de carro a cada seta do teclado (mudança de contexto ao alterar o campo). Agora a troca só acontece pelo botão "Trocar".
- Na Garagem, os botões "Usar no painel" não diziam de qual veículo eram, e nada indicava o carro ativo. Agora o nome acessível inclui o veículo, e o ativo mostra "No painel".
- Contadores em títulos ("Garagem 2", grupos do plano) ganharam a unidade para leitores de tela.
- A quilometragem do painel era lida como "45.000km".
- Na edição de veículo, "Garagem" e "Cancelar" levavam a destinos trocados; agora ambos voltam ao veículo.
- Veículo sem observações mostrava a seção vazia; agora mostra "Sem observações.".
- Sem motorização informada, apareciam "não informada" e "a confirmar" juntos.
- Revalidado após a remoção dos atalhos com dados pessoais: o cadastro começa sempre em branco.

## 3. Serviços

| Passo | Ação | Resultado esperado |
|---|---|---|
| 3.1 | Registrar > Serviço, só a categoria "Revisão ou inspeção geral", data em branco | Salvo; exibido como "Data desconhecida" |
| 3.2 | Novo serviço: óleo, título, data de hoje, 45.500 km, total `189,90`, foto (PNG) | Mensagem "Quilometragem atual atualizada para 45.500 km (substitui a leitura de 45.000 km do mesmo dia)"; foto visível |
| 3.3 | Em "Mais detalhes": preventiva, oficina, duas peças (com "Adicionar outra peça"), peças `120` e mão de obra `69,90` | Detalhe mostra peças e custos |
| 3.4 | Editar com peças `300`, mão de obra `80` e total `100` | Erro: peças e mão de obra somam mais que o total |
| 3.5 | Lista de serviços: busca por nome de peça e filtro por categoria | Resultados atualizam sem recarregar a página |
| 3.6 | Excluir o serviço de 3.1 | Confirmação antes; removido |

Achados (todos corrigidos):

- O km de um serviço era descartado em silêncio quando já havia leitura no mesmo dia. Agora o maior valor do dia prevalece, com mensagem; se o do serviço for menor ou igual, a leitura existente fica e aparece um aviso. Leitura de outro serviço nunca é substituída.
- Mensagens de aviso ganharam estilo próprio (antes usariam o visual de sucesso).
- Anexos: "Baixar" e "Remover" repetidos sem contexto; agora incluem o nome do arquivo, e a imagem avisa que abre em nova aba.
- Peças: linhas com nomes idênticos e falso "obrigatório"; agora cada linha é um grupo "Peça N", e o nome só é exigido quando a linha é usada.
- Recomendação para a nuvem: servir estáticos com nome versionado (hash), para o navegador não usar JS/CSS antigo após atualizações.

## 4. Problemas

| Passo | Ação | Resultado esperado |
|---|---|---|
| 4.1 | Relatar um caso já resolvido: ruído, "barulho de água balançando ao frear", local "Porta traseira", situação "Resolvido", diagnóstico "água acumulada na porta", solução "drenos desobstruídos", causa descartada "tanque de combustível", data em branco | Formulário aceita o relato sem data |
| 4.2 | Salvar | Problema resolvido, com "Causas já descartadas" em destaque |
| 4.3 | Relatar problema: vibração no volante, gravidade alta | Aviso de gravidade alta; cartão do assistente com urgência |
| 4.4 | Adicionar acompanhamento sem texto e sem situação | Erro pedindo texto ou situação |
| 4.5 | Acompanhamento "levei à oficina", situação "Em diagnóstico" | Linha do tempo do problema atualizada |
| 4.6 | "Registrar o serviço que resolveu": balanceamento | Problema passa a "Resolvido", ligado ao serviço |
| 4.7 | Abas Em aberto / Resolvidos / Todos | Contagens e listas coerentes |

## 5. Plano de manutenção

| Passo | Ação | Resultado esperado |
|---|---|---|
| 5.1 | Plano > Ver sugestões: óleo, fluido de freio, bateria, drenos das portas | 4 itens, todos "Sem referência"; nenhuma sugestão traz intervalo |
| 5.2 | Abrir "Troca de óleo" | Aviso "a validar no manual" |
| 5.3 | Editar: a cada 10.000 km e 12 meses, fonte "Manual", conferido | Aviso some |
| 5.4 | Vincular o serviço de óleo do fluxo 3 | Próxima referência: 55.500 km ou daqui a 12 meses |
| 5.5 | Editar para a cada 1.000 km | Situação "Chegando" ou "Passou da referência" conforme o km |
| 5.6 | Programar "Teste da bateria" para daqui a 7 dias | "Programado para …" |
| 5.7 | Descartar "Drenos das portas" com motivo e depois reativar | Vai para "Realizados e descartados" e volta |

## 6. Alertas e preferências

| Passo | Ação | Resultado esperado |
|---|---|---|
| 6.1 | Painel | Alertas do plano no topo; contador no sino |
| 6.2 | Abrir o sino | Lista com motivo e prioridade de cada alerta; nenhum afirma defeito |
| 6.3 | Alertas > Configurar: desmarcar prioridade baixa, antecedência 500 km | Alertas de prioridade baixa somem |
| 6.4 | Voltar a exibir prioridade baixa | Alertas voltam |

## 7. Linha do tempo e finanças

| Passo | Ação | Resultado esperado |
|---|---|---|
| 7.1 | Histórico | Serviços, problemas, acompanhamentos e km agrupados por mês; "Pela frente" com itens do plano |
| 7.2 | Filtrar "Serviços" e depois situação "Corretiva" | Lista muda sem recarregar; endereço reflete o filtro |
| 7.3 | Finanças (12 meses) | Total, média mensal, preventiva x corretiva, categorias e gráfico mensal |
| 7.4 | Trocar para "Todo o período" | Gráfico por ano; serviços sem valor contados à parte |
| 7.5 | Previsão de 12 meses | Itens do plano com custo estimado (informar um custo em 5.x, se necessário) |

## 8. Assistente de manutenção

| Passo | Ação | Resultado esperado |
|---|---|---|
| 8.1 | Registrar > "Não sei o que é": ruído, "barulho de líquido na traseira ao frear", local "Porta traseira" | Primeira possibilidade: água na porta; combustível em "Já descartado"; pergunta "Da outra vez a solução foi…" |
| 8.2 | Nova análise: "pedal baixo e chiado ao frear" | Urgência alta com justificativa e recomendação de avaliação profissional |
| 8.3 | Salvar a análise de 8.1 como problema | Formulário preenchido; problema salvo com cartão do assistente |
| 8.4 | Assistente > Perfil de uso: parado vários dias e carga frequente | Sugestões pelo uso; "Adicionar ao plano" funciona |
| 8.5 | Revisão do carro | Recomendações por tipo, itens sem histórico, itens que dependem do tempo, peças do último ano |
| 8.6 | Resumo para o mecânico | Veículo, problemas com perguntas, plano e serviços; botão de impressão |

## 9. Seus dados: CSV, backup e restauração

| Passo | Ação | Resultado esperado |
|---|---|---|
| 9.1 | Mais opções > Seus dados > planilha de serviços | Download do CSV com separador `;` e valores `189,90` |
| 9.2 | Baixar backup | Download do `.zip`; "Último backup" atualizado; alerta de backup some |
| 9.3 | Tentar restaurar nesta conta | Opção indisponível (conta já tem veículos) |
| 9.4 | Em uma segunda instância zerada (porta 8002), criar conta e restaurar o `.zip` | "Backup restaurado"; veículos, serviços, problemas, plano, anexos e perfil de uso presentes |

## 10. Celular, teclado e acessibilidade

| Passo | Ação | Resultado esperado |
|---|---|---|
| 10.1 | Largura de 390 px: navegar pela barra inferior | Início, Plano, Registrar, Serviços e Problemas; sem rolagem horizontal |
| 10.2 | Registrar serviço rápido no celular | Botão Salvar sempre visível acima da barra inferior |
| 10.3 | Tab a partir do topo | "Ir para o conteúdo" aparece; foco visível em links, botões e opções |
| 10.4 | Enviar formulário com erro | Foco vai para o primeiro campo inválido; erro anunciado |
| 10.5 | Larguras de 1024 e 1440 px | Menu superior sem transbordar |
