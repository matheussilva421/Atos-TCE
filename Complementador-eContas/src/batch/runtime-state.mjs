export function createDriveTracker(now = () => Date.now()) {
  let last = null;
  return {
    record(result) {
      last = {
        state: typeof (result && result.state) === 'string' ? result.state.slice(0, 32) : 'UNKNOWN',
        steps: Number.isSafeInteger(result && result.steps) ? result.steps : 0,
        at: now(),
      };
    },
    fail(error) {
      last = {
        state: 'ERROR',
        steps: 0,
        code: (error && error.code) || 'DRIVE_FAILED',
        at: now(),
      };
    },
    read() {
      return last ? { ...last } : null;
    },
  };
}
