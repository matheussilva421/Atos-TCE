# Atos-TCE F4 — Human Completion Events and Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconhecer conclusões de atos somente quando o portal as comprovar após clique exclusivamente humano, recuperar notificações perdidas e manter encerramento de processos manual.

**Architecture:** Observador MV3 passivo e fail-closed; evento confirmado é envelopado com identidade exata, protegido em fila local até ACK autenticado e aplicado idempotentemente em SQLite pela Mesa. Processo tem status separado e só muda com ação humana.

**Tech Stack:** MV3 JavaScript/WebCrypto, chrome.storage, Python 3/Windows DPAPI/SQLite, API autenticada, unittest e Node node:test.

**Spec:** `docs/superpowers/specs/2026-10-20-atos-tce-mesa-extensao-json-portal-lab-design.md` §§10, 14–16. Depende F2/F3; comprovação real no Portal Lab/F5 antes de habilitação.

## Global Constraints
- Nenhum script, agente, controller ou extensão clica `Complementar Ato`, assina, tramita, envia ou simula confirmação.
- Se não houver evidência positiva inequívoca vinculada a ato identificável, status `COMPLETION_UNCONFIRMED`, sem evento de sucesso.
- `FILL_RESULT` é efêmero/best effort, **não** persistir seus valores; fila durável é exclusiva de `ACT_CONFIRMED_COMPLETED`.
- A fila só armazena ciphertext com identidade mínima; `chrome.storage.local` isoladamente não é criptografia. Chave privada nunca vai para a extensão.
- Limite arquitetural aprovado: até 512 eventos, retenção operacional até 7 dias; ao atingir limite/prazo sem ACK, não descartar silenciosamente, exigir reconciliação.
- Encerramento global de processo sempre por ação humana; pendências exigem justificativa explícita.
- Testes offline nunca provam que o portal emitiu confirmação; gate REA/Portal Lab é independente e não automatiza clique final.

## Review Focus
1. Formulário desapareceu/retornou à lista após clique: sozinho nunca prova conclusão (T1).
2. Identidade de ato ausente ou ambígua não pode ser sintetizada só com processo/interessado (T1).
3. Mesa indisponível/sem chave legítima: não armazenar plaintext sob pretexto de proteção (T2/T3).
4. ACK perdido e retransmissão duplicada não cria conclusão dupla (T3/T4).
5. Fechamento humano do processo com pendência não reescreve estados dos atos (T5).

---

### Task F4-T1: Observador passivo de conclusão inequívoca

**Files:** Create `extension/content/conclusion-observer.js`, `extension/tests/conclusion-observer.test.mjs`; Modify `extension/background/router.js` somente para transportar resultado de leitura.

**Interfaces:** `classifyCompletionEvidence({before,after,identity,portalSignals}) -> {status:'CONFIRMED'|'UNCONFIRMED',actId?,evidenceKind?}`. O leitor **não** tem referência a botão submit nem função de click.

- [ ] **Step 1 — RED:** `missing_act_identity_is_unconfirmed`, `form_disappearance_alone_is_unconfirmed`, `positive_portal_proof_requires_exact_act`: assert.equal(classifyCompletionEvidence({before,after:empty,...}).status,"UNCONFIRMED").
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/conclusion-observer.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Classificador puro que só aceita um conjunto versionado de provas positivas observadas pelo REA/Portal Lab e vinculadas a actId; enquanto nenhuma prova real for homologada, manter bloqueado por feature gate.
- [ ] **Step 4 — Verificar:** Focado PASS, `(cd extension && node --test)` PASS; teste estático que `protocol.js` não possui `SUBMIT`, `SEND`, `FINALIZE`.
- [ ] **Step 5 — Commit:** `git add extension/content/conclusion-observer.js extension/tests/conclusion-observer.test.mjs extension/background/router.js && git commit -m "feat: classify passive portal completion evidence"`.
- [ ] **Step 6 — Review:** Fresh reviewer deve rejeitar proxies falsos de sucesso, timers, heurística de desaparecimento ou código de clique final.

### Task F4-T2: Identidade criptográfica e envelope protegido

**Files:** Create `app/area_restrita/completion_keys.py`, `tests/test_completion_keys.py`, `extension/lib/completion-envelope.js`, `extension/tests/completion-envelope.test.mjs`; Modify `app/api/server.py` apenas para endpoint autenticado de chave pública.

**Interfaces:** `get_or_create_completion_keypair(user_scope) -> {public_jwk,key_id}`, `decrypt_completion_envelope(envelope) -> dict`; `sealCompletionEvent(publicJwk,keyId,event) -> Promise<{keyId,nonce,ciphertext,wrappedKey}>`.

- [ ] **Step 1 — RED:** Python `test_private_key_protected_for_current_windows_user`, JS `never_persist_unsealed_event`: assert ciphertext não contém processo real de fixture; chave privada não aparece em resposta HTTP; assinatura de origem autentica chave pública via sessão Mesa.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_completion_keys -v` e `node --test extension/tests/completion-envelope.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Gerar chave assimétrica com armazenamento privado por usuário via DPAPI e ACL; na extensão, envelope AES-GCM por evento com chave AES envelopada por RSA-OAEP public JWK obtida do endpoint autenticado; keyId verificável e zero escrita plaintext em disco.
- [ ] **Step 4 — Verificar:** Focados PASS; testes Windows de DPAPI rodados em Windows, nunca marcados PASS se executados como SKIP em outro OS; `python -m unittest tests.test_api_server -q` PASS.
- [ ] **Step 5 — Commit:** `git add app/area_restrita/completion_keys.py tests/test_completion_keys.py extension/lib/completion-envelope.js extension/tests/completion-envelope.test.mjs app/api/server.py && git commit -m "feat: protect completion event envelopes"`.
- [ ] **Step 6 — Review:** Fresh security reviewer valida ciclo de chave, nonce aleatório, cifragem autenticada, replay, origem do endpoint, rotação e zero plaintext em storage/log.

### Task F4-T3: Fila MV3 limitada e retransmissão por ACK

**Files:** Create `extension/background/pending-completions.js`, `extension/tests/pending-completions.test.mjs`; Modify `extension/background/router.js`.

**Interfaces:** `enqueueConfirmedCompletion(encryptedEnvelope) -> Promise<{status}>`, `deliverPendingCompletions(sendFn) -> Promise<{acknowledged, pending}>`. Máx 512, até 7 dias com alerta/reconciliação em vez de descarte silencioso.

- [ ] **Step 1 — RED:** `restart_keeps_encrypted_pending_events`, `lost_ack_retries_same_event_id`, `queue_full_warns_without_dropping`, `cannot_enqueue_unconfirmed_event`: assert que reenvio retém mesmo eventId e nunca duplica por geração de tentativa.
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/pending-completions.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Persistir apenas ciphertext+metadados mínimos com lease de envio, ACK exato, backoff, idempotency key e sobrevivência a restart MV3; falha de chave/proteção → status visível para reconciliação manual, não false success.
- [ ] **Step 4 — Verificar:** Focado PASS e `(cd extension && node --test)` PASS; disparar simulações de perda de ack, corrupção e idade >7 dias.
- [ ] **Step 5 — Commit:** `git add extension/background/pending-completions.js extension/tests/pending-completions.test.mjs extension/background/router.js && git commit -m "feat: reliably relay encrypted confirmed completions"`.
- [ ] **Step 6 — Review:** Reviewer verifica plaintext, retained ack, limite de armazenamento e reenvio de evento incorreto.

### Task F4-T4: Receptor Mesa idempotente e confirmação de recebimento

**Files:** Create `app/area_restrita/completion_events.py`, `tests/test_completion_events.py`; Modify `app/api/server.py` e `app/core/store.py` para transação dedicada.

**Interfaces:** `accept_confirmed_completion(store, envelope, session) -> {accepted:bool,ack_id:str}`. Dedup key ligada a actId, chave da origem, evento e prova observada; ACK só depois de commit SQLite.

- [ ] **Step 1 — RED:** `same_event_twice_one_completed_act`, `ack_is_not_sent_before_commit`, `mismatched_identity_is_rejected`: assert count(eventId)=1 e status do ato persistido apenas quando prova/identidade são válidas.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_completion_events -v` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Decriptar com chave local, validar schema/prova/identity, transação SQL com constraint de unicidade e ACK autenticado somente após commit; não criar conclusão de processo.
- [ ] **Step 4 — Verificar:** Focado PASS e `python -m unittest tests.test_api_server tests.test_completion_events -q` PASS; simular crash antes do ACK.
- [ ] **Step 5 — Commit:** `git add app/area_restrita/completion_events.py app/api/server.py app/core/store.py tests/test_completion_events.py && git commit -m "feat: apply confirmed act events idempotently"`.
- [ ] **Step 6 — Review:** Fresh reviewer examina transação atômica, chaves únicas, spoofing de evidência, crash/replay e dados em logs.

### Task F4-T5: Encerramento de processo humano e reconciliação de pendências

**Files:** Create `app/core/process_closure.py`, `tests/test_process_closure.py`; Modify `app/web/app.js` e `app/web/tests/ui-wiring.test.mjs`.

**Interfaces:** `request_process_closure(process_id, operator_id, justification: str|None) -> ClosureResult`; não altera tabelas de status individual do ato.

- [ ] **Step 1 — RED:** `pending_acts_require_explicit_justification`, `closing_process_does_not_fake_act_completion`: assert rejected sem justificativa quando há unconfirmed/pending; após justificar, status global muda e atos permanecem intactos.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_process_closure -v` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Mostrar diagnóstico de pendências na Mesa, botão humano explícito e justificativa auditada; garantir guarda de versão e ausência de alteração de `ACT_CONFIRMED_COMPLETED`.
- [ ] **Step 4 — Verificar:** Focado PASS; `python -m unittest discover -s tests -p "test_*.py" -q` e `node --test app/web/tests/*.test.mjs` PASS.
- [ ] **Step 5 — Commit:** `git add app/core/process_closure.py tests/test_process_closure.py app/web/app.js app/web/tests/ui-wiring.test.mjs && git commit -m "feat: require human justification to close pending processes"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica fechamento inadvertido, justificativa vazia ou fabricada e separação ato/processo.

## F4 exit gate
- [ ] Fluxo de prova positiva permanece DESABILITADO até REA confirmar sinais reais seguros; fixture não qualifica.
- [ ] Criptografia validada no Windows-alvo, fila limitada sem descarte silencioso, ACK/dedup, estados de erro explícitos.
- [ ] Nenhuma ação L3 automatizada; operador continua único executor da conclusão.
- [ ] Cada task tem RED/GREEN, commit/reviewer; Python/extension/web e privacidade PASS.
- [ ] Nenhuma capacidade promovida sem F5 Reliability Reset 20/20+20/20.
