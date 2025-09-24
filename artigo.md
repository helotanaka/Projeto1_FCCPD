# Sistema Bancário Distribuído com Controle de Concorrência

Alunos:
ANTONIO PAULO ARAUJO DE BARROS E SILVA - apabs@cesar.school
DAVI GOMES FERREIRA RUY DE ALMEIDA - dgfra@cesar.school
HELOÍSA TANAKA FERNANDES - htf@cesar.school
JOÃO PEDRO FONTES FERREIRA - jpff2@cesar.school
LEONARDO CARDOSO DE CARVALHO GUEDES - lccg@cesar.school

## Trabalho

Este trabalho foi feito para a disciplina de Fundamentos de Computação Concorrente, Paralela e Distribuída da CESAR School. Neste repositório, apresenta-se a implementação de um sistema bancário distribuído utilizando arquitetura cliente-servidor, com foco na aplicação de conceitos de concorrência e paralelismo.

O sistema desenvolvido em Python permite operações bancárias básicas (depósito, saque, transferência e consulta de saldo) garantindo consistência e persistência com logs Write-Ahead. A solução demonstra a aplicação prática de threads, locks, comunicação via sockets TCP/IP e tratamento de condições de corrida em sistemas distribuídos.

## 1. Introdução

Sistemas distribuídos são fundamentais na computação moderna, permitindo que aplicações executem em múltiplas máquinas de forma coordenada. Em ambientes bancários, a necessidade de processamento concorrente e garantias de consistência tornam-se críticas para o funcionamento seguro do sistema.

O presente trabalho implementa um sistema bancário distribuído que explora os desafios de concorrência em operações financeiras, demonstrando como múltiplos clientes podem realizar transações simultâneas mantendo a integridade dos dados. A arquitetura cliente-servidor escolhida permite escalabilidade e separação de responsabilidades.

Os principais objetivos são implementar:

- (1) Comunicação entre processos via sockets;
- (2) Controle de concorrência com threads e locks;
- (3) Atomicidade em transferências bancárias.

## 2. Metodologia

### 2.1 Arquitetura do Sistema

O sistema adota uma arquitetura cliente-servidor tradicional, onde:

- **Servidor (`server.py`)**: Processo central que gerencia o estado das contas bancárias, processa requisições e mantém a consistência dos dados
- **Cliente (`client.py`)**: Interface de linha de comando que permite aos usuários realizar operações bancárias

### 2.2 Comunicação Distribuída

A comunicação entre cliente e servidor utiliza protocolo TCP/IP com formato JSON sobre sockets. Cada mensagem é enviada como uma linha terminada por `\n`, implementando um protocolo simples mas eficaz:

```
Cliente → Servidor: {"cmd": "deposit", "user": "alice", "amount": 5000}
Servidor → Cliente: {"ok": true, "before": 10000, "after": 15000}
```

### 2.3 Controle de Concorrência

O servidor implementa um sistema sofisticado de controle de concorrência:

#### 2.3.1 Threading por Cliente

Cada conexão cliente é atendida por uma thread separada:

```python
threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
```

#### 2.3.2 Locks

O sistema utiliza locks por conta bancária para maximizar paralelismo:

- **Lock por conta**: Cada conta possui seu próprio `threading.Lock()`
- **Lock global**: `threading.RLock()` protege estruturas compartilhadas
- **Prevenção de deadlock**: Locks são adquiridos em ordem determinística (linha 114)

```python
u1, u2 = sorted([from_user, to_user])  # Ordem determinística
l1, l2 = self._get_lock(u1), self._get_lock(u2)
with l1:
    with l2:  # Sempre na mesma ordem
        # Operação atômica
```

### 2.4 Persistência e Recuperação

O sistema implementa dois mecanismos de persistência:

1. **Write-Ahead Log (WAL)**: Todas as operações são registradas em `transactions.log` antes da confirmação
2. **Snapshots**: Estado atual das contas salvo periodicamente em `state.json`

### 2.5 Operações Suportadas

- **init_accounts**: Inicialização de contas com saldos iniciais
- **balance**: Consulta de saldo
- **deposit**: Depósito em conta
- **withdraw**: Saque com verificação de fundos
- **transfer**: Transferência entre contas com atomicidade

## 3. Resultados

### 3.1 Funcionalidade Básica

Os testes demonstram o funcionamento correto das operações:

```bash
$ python client.py 127.0.0.1 5000 init init_accounts.json
{'ok': True, 'accounts': {'alice': 100000, 'bob': 50000}}

$ python client.py 127.0.0.1 5000 balance alice
{'ok': True, 'user': 'alice', 'balance': 100000}

$ python client.py 127.0.0.1 5000 deposit alice 2500
{'ok': True, 'before': 100000, 'after': 102500}

$ python client.py 127.0.0.1 5000 transfer alice bob 777
{'ok': True, 'from': {'user': 'alice', 'before': 102500, 'after': 101723},
           'to': {'user': 'bob', 'before': 50000, 'after': 50777}}
```

### 3.2 Persistência

O WAL registra todas as transações:

```json
{"tx": "deposit", "tx_id": "f5a6dfbe-9750-4ade-a1c5-dcb1b47db731", "user": "alice", "amount": 2500, "after": 102500}
{"tx": "transfer", "tx_id": "5f531981-0866-4a29-80f8-2d2e07bc69c1", "from": "alice", "to": "bob", "amount": 777, "after_from": 101723, "after_to": 50777}
```

### 3.3 Concorrência

O servidor aceita múltiplas conexões simultâneas, cada uma processada em thread separada. O sistema de locks garante que operações em contas diferentes possam ocorrer paralelamente, enquanto operações na mesma conta são serializadas.

### 3.4 Robustez

- **Validação de entrada**: Valores negativos e operações inválidas são rejeitadas.
- **Verificação de fundos**: Saques e transferências verificam saldo suficiente.
- **Tratamento de erros**: Erros de rede e parsing são reconhecidos e tratados.
- **Shutdown limpo**: Comando `shutdown` permite encerramento controlado.

## 4. Conclusão

O sistema implementado demonstra com sucesso a aplicação de conceitos fundamentais de sistemas distribuídos, concorrência e paralelismo. A arquitetura cliente-servidor com controle granular de locks permite operações bancárias seguras e eficientes.

Os resultados mostram que é possível construir um sistema distribuído robusto utilizando ferramentas simples como sockets TCP e threading, desde que os mecanismos de sincronização sejam cuidadosamente projetados. A implementação de WAL e idempotência adiciona camadas importantes de confiabilidade.

Este trabalho fornece uma base sólida para compreensão prática dos desafios enfrentados em sistemas distribuídos reais, especialmente em domínios que exigem forte consistência como sistemas financeiros.

## Diagrama da Arquitetura

# A FAZER

## Fluxo de Operação - Realizando Transferência - Exemplo

```
1. Cliente A → Servidor: {"cmd": "transfer", "from": "alice", "to": "bob", "amount": 100}
2. Servidor: Adquire lock da alice
3. Servidor: Adquire lock do bob
4. Servidor: Verifica saldo da alice
5. Servidor: Debita da alice, credita para bob
6. Servidor: Libera locks
7. Servidor: Escreve no WAL
8. Servidor → Return Cliente A: {"ok": true, "from": {...}, "to": {...}}
```
