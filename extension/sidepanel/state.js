export function describeMesaStatus(status) {
  if (status?.ok && status?.paired) {
    return {
      paired: true,
      tone: "ok",
      label: "Mesa conectada",
      diagnostic: "Pronto: a Mesa comanda o trabalho e você confirma o ato no portal.",
    };
  }

  if (status?.status === 0 || status?.error === "fetch_failed") {
    return {
      paired: false,
      tone: "error",
      label: "Mesa não encontrada",
      diagnostic: "Inicie a Mesa local; a conexão será tentada novamente automaticamente.",
    };
  }

  return {
    paired: false,
    tone: "warn",
    label: "Conectando à Mesa…",
    diagnostic: "A conexão automática está sendo estabelecida.",
  };
}
