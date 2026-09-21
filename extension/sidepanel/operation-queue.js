export function createSerialQueue() {
  let tail = Promise.resolve();

  return {
    run(task) {
      const next = tail.then(task, task);
      tail = next.catch(() => undefined);
      return next;
    },
  };
}
