# RELATORIO_CORRECOES_POPULADOR.md

## STATUS

[x] Auditoria estrutural realizada  
[x] Schema analisado  
[x] Constraints principais mapeadas  
[x] Colisões de dados únicos corrigidas  
[x] CPF protegido  
[x] Emails protegidos  
[x] Hashes de fotos protegidos  
[x] Camada de geradores únicos criada  

## Erros encontrados

### duplicate key uq_usuarios_cpf

**Causa:** geração aleatória de CPF sem memória de valores já utilizados.

**Correção:** criado `utils/unique_generator.py` com controle de colisões em memória.

### Hash de fotos

**Causa:** dependência de combinação aleatória para SHA256.

**Correção:** geração centralizada com entropia adicional.

## Arquitetura adicionada

```
src/utils/
 └── unique_generator.py
```

Responsabilidades:

- CPF único
- email único
- hash SHA256 único
- tokens seguros
- idempotency keys UUID

## Observação de execução

A validação completa das 10 execuções consecutivas depende de um PostgreSQL configurado com o schema ECOCIENTE disponível no ambiente de execução.

# RELATÓRIO DE COBERTURA ECOCIENTE V2

## Alterações

- Volumetria ampliada para testes de dashboard, ranking e paginação.
- Usuários ativos/inativos.
- Mais condomínios residenciais e comerciais.
- Mais cooperativas e pontos de coleta.
- Distribuição geográfica ampliada.

## Status

[x] Auditoria realizada
[x] Schema analisado
[x] Massa expandida
[x] Cenários adicionais criados

## Observação

A nova carga mantém a arquitetura original do Populador e altera somente parâmetros e geradores existentes.
