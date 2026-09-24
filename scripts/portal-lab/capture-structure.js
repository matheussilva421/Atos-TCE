(() => {
  const doc = document;
  const win = window;

  const readFramePath = () => {
    const path = [];
    let current = win;
    for (let depth = 0; depth < 32; depth += 1) {
      let frameElement;
      try {
        frameElement = current.frameElement;
      } catch {
        path.unshift("cross-origin-boundary");
        break;
      }
      if (!frameElement) break;

      const tag = String(frameElement.tagName || "iframe").toLowerCase();
      const id = typeof frameElement.id === "string" ? frameElement.id.trim() : "";
      const name = typeof frameElement.name === "string" ? frameElement.name.trim() : "";
      path.unshift(id ? `${tag}#${id}` : name ? `${tag}[name=${name}]` : tag);
      try {
        const parent = current.parent;
        if (!parent || parent === current) break;
        current = parent;
      } catch {
        path.unshift("cross-origin-boundary");
        break;
      }
    }
    return path;
  };

  const attribute = (element, name) => {
    try {
      if (typeof element.getAttribute === "function") {
        return element.getAttribute(name) || "";
      }
    } catch {
      return "";
    }
    const value = element[name];
    return typeof value === "string" ? value : "";
  };

  const controls = Array.from(doc.querySelectorAll("input,select,textarea,button"), (element) => {
    const tag = String(element.tagName || "").toLowerCase();
    const type = attribute(element, "type");
    const optionCount = tag === "select" && element.options ? element.options.length : 0;
    return {
      tag,
      id: attribute(element, "id") || (typeof element.id === "string" ? element.id : ""),
      name: attribute(element, "name") || (typeof element.name === "string" ? element.name : ""),
      type: type || (typeof element.type === "string" ? element.type : ""),
      disabled: element.disabled === true,
      readOnly: element.readOnly === true,
      optionCount,
    };
  });

  return {
    route: typeof win.location?.pathname === "string" ? win.location.pathname : "/",
    readyState: String(doc.readyState || ""),
    framePath: readFramePath(),
    controls,
    sentinels: [],
    childFrameCount: doc.querySelectorAll("iframe,frame").length,
  };
})()
