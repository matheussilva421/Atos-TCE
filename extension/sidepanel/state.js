export function describeMesaStatus(status) {
  if (status?.ok && status?.paired) {
    return {
      paired: true,
      stale: false,
      tone: "ok",
      label: "Mesa conectada",
      diagnostic: "Pronto: a Mesa comanda o trabalho e você confirma o ato no portal.",
    };
  }

  if (status?.status === 401) {
    return {
      paired: false,
      stale: true,
      tone: "error",
      label: "Mesa: pareamento deste perfil recusado",
      diagnostic:
        "O token deste perfil foi recusado. Na Mesa, clique em Reparear extensão, confirme e digite o novo código neste painel.",
    };
  }

  return {
    paired: false,
    stale: false,
    tone: "error",
    label: "Mesa indisponível ou token recusado",
    diagnostic: "Pareie com o código de seis dígitos exibido na Mesa.",
  };
}
