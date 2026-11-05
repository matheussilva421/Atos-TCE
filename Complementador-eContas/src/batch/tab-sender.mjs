import { retryAsync } from '../shared/retry.mjs';

/**
 * Envia mensagem para uma aba exigindo resposta real. Se o content script
 * esperado ainda não carregou, outros scripts respondem `undefined`; nesse caso
 * a tentativa é repetida até o limite.
 */
export function createTabSender(sendMessage, options = {}) {
  const attempts = Number.isSafeInteger(options.attempts) ? options.attempts : 80;
  const delayMs = Number.isFinite(options.delayMs) ? options.delayMs : 250;
  return (tabId, payload) => retryAsync(async () => {
    const response = await sendMessage(tabId, payload);
    if (response === undefined || response === null) {
      const error = new Error('CONTENT_SCRIPT_NOT_READY');
      error.code = 'CONTENT_SCRIPT_NOT_READY';
      throw error;
    }
    return response;
  }, { attempts, delayMs, sleep: options.sleep });
}
