/**
 * Repete uma operação assíncrona um número limitado de vezes com intervalo fixo.
 * Usado para aguardar o content script de uma aba recém-aberta ficar disponível.
 */
export async function retryAsync(operation, options = {}) {
  const attempts = Number.isSafeInteger(options.attempts) && options.attempts > 0
    ? options.attempts
    : 20;
  const delayMs = Number.isFinite(options.delayMs) ? Math.max(0, options.delayMs) : 250;
  const sleep = options.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  let lastError = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await operation(attempt);
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) {
        await sleep(delayMs);
      }
    }
  }
  throw lastError || new Error('RETRY_EXHAUSTED');
}
