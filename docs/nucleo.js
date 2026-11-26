// Regras do jogo e features. Porte fiel do prototipo.py (unidades em CELULAS).
// Mesmo modulo no navegador (jogo) e no servidor (validacao por replay).

export const NOMES = ["Cima", "Baixo", "Esquerda", "Direita"]; // indices usados no envio
export const DIRS = {
  Cima: [0, -1],
  Baixo: [0, 1],
  Esquerda: [-1, 0],
  Direita: [1, 0],
};
export const TABULEIROS = [
  [40, 30], // paisagem (o tabuleiro original 800x600 / 20px)
  [30, 40], // retrato (mesmo jogo, girado)
];
export const RESULTADOS = ["parede", "corpo", "venceu", "abandonada"];

const igual = (a, b) => a[0] === b[0] && a[1] === b[1];

export function inicioDe(cols, linhas) {
  return [cols / 2, linhas / 2]; // (400,300) em pixels -> (20,15)
}

export function criarEstado(cols, linhas) {
  return {
    cols,
    linhas,
    cobra: [inicioDe(cols, linhas)],
    dirPasso: "Direita", // direcao do ultimo passo executado
    fruta: null,
    pontuacao: 0,
    momento: 0,
    fim: false,
    venceu: false,
    resultado: null, // "parede" | "corpo" | "venceu"
  };
}

function fora(est, c) {
  return c[0] < 0 || c[0] >= est.cols || c[1] < 0 || c[1] >= est.linhas;
}

// Parede ou corpo. A ponta do rabo sai do lugar no proximo passo, entao nao conta.
function ehPerigo(est, c) {
  if (fora(est, c)) return true;
  const corpo = est.cobra.length > 1 ? est.cobra.slice(0, -1) : [];
  return corpo.some((s) => igual(s, c));
}

export function gerarFruta(est, rnd = Math.random) {
  const ocupado = new Set(est.cobra.map((s) => s[0] + "," + s[1]));
  const livres = [];
  for (let x = 0; x < est.cols; x++)
    for (let y = 0; y < est.linhas; y++)
      if (!ocupado.has(x + "," + y)) livres.push([x, y]);
  return livres.length ? livres[Math.floor(rnd() * livres.length)] : null;
}

// Mesmas colunas gravadas nos CSVs pelo prototipo.py (features.COLUNAS_ABSOLUTAS).
export function features(est) {
  const [hx, hy] = est.cobra[0];
  const dx = est.fruta ? est.fruta[0] - hx : 0;
  const dy = est.fruta ? est.fruta[1] - hy : 0;
  const perigo = (nome) =>
    ehPerigo(est, [hx + DIRS[nome][0], hy + DIRS[nome][1]]) ? 1 : 0;
  return {
    dx,
    dy,
    dir_cima: est.dirPasso === "Cima" ? 1 : 0,
    dir_baixo: est.dirPasso === "Baixo" ? 1 : 0,
    dir_esquerda: est.dirPasso === "Esquerda" ? 1 : 0,
    dir_direita: est.dirPasso === "Direita" ? 1 : 0,
    perigo_cima: perigo("Cima"),
    perigo_baixo: perigo("Baixo"),
    perigo_esquerda: perigo("Esquerda"),
    perigo_direita: perigo("Direita"),
    TamanhoCobrinha: est.cobra.length,
  };
}

// Proibe meia-volta (so com a cobra maior que 1), comparando com o ultimo passo executado.
export function movimentoValido(est, nome, referencia = est.dirPasso) {
  if (est.cobra.length <= 1) return true;
  const a = DIRS[nome];
  const b = DIRS[referencia];
  return !(a[0] === -b[0] && a[1] === -b[1]);
}

// Executa um passo (porte de atualizar_jogo, ja com a direcao decidida).
// escolherFruta(est) devolve a proxima fruta; no replay do servidor e omitida
// (a fruta fica pendente ate o proximo registro informa-la).
export function passo(est, nome, escolherFruta = null) {
  est.momento += 1;
  const feats = features(est);
  const d = DIRS[nome];
  const [hx, hy] = est.cobra[0];
  const nova = [hx + d[0], hy + d[1]];

  const comeu = est.fruta !== null && igual(nova, est.fruta);
  const corpo = comeu ? est.cobra : est.cobra.slice(0, -1);
  const bateuParede = fora(est, nova);
  const bateuCorpo = corpo.some((s) => igual(s, nova));

  const registro = { ...feats, decisao: nome, Momento: est.momento };

  if (bateuParede || bateuCorpo) {
    est.fim = true;
    est.resultado = bateuParede ? "parede" : "corpo";
  } else {
    est.cobra.unshift(nova);
    est.dirPasso = nome;
    if (comeu) {
      est.pontuacao += 1;
      if (est.cobra.length >= est.cols * est.linhas) {
        est.venceu = true;
        est.fim = true;
        est.resultado = "venceu";
        est.fruta = null;
      } else {
        est.fruta = escolherFruta ? escolherFruta(est) : null;
      }
    } else {
      est.cobra.pop();
    }
  }
  return registro;
}

// --------------------------------------------------------------------------
// Replay: recria a partida a partir do envio e recalcula TODAS as features.
// Nada vindo do cliente alem da fruta (dx,dy) e da decisao e confiado.
// passos: [[dx, dy, indiceDaDecisao], ...]
// --------------------------------------------------------------------------
export function reproduzir(p) {
  const est = criarEstado(p.cols, p.linhas);
  const linhas = [];

  for (let i = 0; i < p.passos.length; i++) {
    if (est.fim) return { ok: false, erro: "passos apos o fim da partida" };

    const [dx, dy, di] = p.passos[i];
    const nome = NOMES[di];
    const [hx, hy] = est.cobra[0];
    const fruta = [hx + dx, hy + dy];

    if (est.fruta === null) {
      if (fora(est, fruta) || est.cobra.some((s) => igual(s, fruta)))
        return { ok: false, erro: `fruta invalida no passo ${i + 1}` };
      est.fruta = fruta;
    } else if (!igual(est.fruta, fruta)) {
      return { ok: false, erro: `fruta mudou sem ser comida no passo ${i + 1}` };
    }

    if (!movimentoValido(est, nome))
      return { ok: false, erro: `meia-volta no passo ${i + 1}` };

    linhas.push(passo(est, nome));
  }

  const esperado = p.resultado;
  if (esperado === "abandonada") {
    if (est.fim) return { ok: false, erro: "abandonada, mas a partida ja tinha acabado" };
  } else if (est.resultado !== esperado) {
    return { ok: false, erro: `resultado ${esperado} nao confere (${est.resultado})` };
  }
  if (est.pontuacao !== p.pontuacao) return { ok: false, erro: "pontuacao nao confere" };

  return { ok: true, linhas, pontuacao: est.pontuacao, resultado: esperado };
}

// --------------------------------------------------------------------------
// IA: floresta exportada por exportar_modelo_web.py (media das probabilidades
// das arvores, igual ao predict() do scikit-learn).
// --------------------------------------------------------------------------
const VET = DIRS;
const esq = (v) => [v[1], -v[0]];
const dir = (v) => [-v[1], v[0]];
const nomeDe = (v) => NOMES.find((n) => igual(VET[n], v));
const COL_PERIGO = {
  Cima: "perigo_cima",
  Baixo: "perigo_baixo",
  Esquerda: "perigo_esquerda",
  Direita: "perigo_direita",
};

// features.para_relativo
export function paraRelativo(f, nomeDirecao) {
  const frente = VET[nomeDirecao];
  const e = esq(frente);
  const d = dir(frente);
  return [
    f.dx * frente[0] + f.dy * frente[1], // fruta_frente
    f.dx * e[0] + f.dy * e[1], // fruta_esq
    f[COL_PERIGO[nomeDirecao]], // rel_perigo_frente
    f[COL_PERIGO[nomeDe(e)]], // rel_perigo_esq
    f[COL_PERIGO[nomeDe(d)]], // rel_perigo_dir
    f.TamanhoCobrinha,
  ];
}

export function preverAcao(modelo, x) {
  const k = modelo.classes.length;
  const soma = new Array(k).fill(0);
  for (const a of modelo.arvores) {
    let i = 0;
    while (a.f[i] >= 0) i = x[a.f[i]] <= a.t[i] ? i + 1 : a.r[i];
    const base = a.t[i] * k;
    for (let c = 0; c < k; c++) soma[c] += a.p[base + c];
  }
  let melhor = 0;
  for (let c = 1; c < k; c++) if (soma[c] > soma[melhor]) melhor = c;
  return modelo.classes[melhor];
}

// features.absoluto_de
export function absolutoDe(acao, nomeDirecao) {
  const frente = VET[nomeDirecao];
  if (acao === "Esquerda") return nomeDe(esq(frente));
  if (acao === "Direita") return nomeDe(dir(frente));
  return nomeDirecao;
}

const CACHE_CICLOS_HAMILTONIANOS = new Map();

function obterCicloHamiltoniano(cols, linhas) {
  const chave = `${cols}x${linhas}`;

  if (CACHE_CICLOS_HAMILTONIANOS.has(chave)) {
    return CACHE_CICLOS_HAMILTONIANOS.get(chave);
  }

  if (cols < 2 || linhas < 2 || cols % 2 !== 0) {
    throw new Error(
      `Ciclo Hamiltoniano não implementado para ${cols}x${linhas}`
    );
  }

  const caminho = [];

  // Primeira linha: esquerda para direita.
  for (let x = 0; x < cols; x++) {
    caminho.push([x, 0]);
  }

  // Demais linhas, alternando o sentido.
  for (let y = 1; y < linhas; y++) {
    if (y % 2 === 1) {
      for (let x = cols - 1; x >= 1; x--) {
        caminho.push([x, y]);
      }
    } else {
      for (let x = 1; x < cols; x++) {
        caminho.push([x, y]);
      }
    }
  }

  // Fecha o ciclo pela primeira coluna.
  caminho.push([0, linhas - 1]);

  for (let y = linhas - 2; y >= 1; y--) {
    caminho.push([0, y]);
  }

  if (caminho.length !== cols * linhas) {
    throw new Error("Ciclo Hamiltoniano com quantidade incorreta de casas");
  }

  const inicio = [
    Math.floor(cols / 2),
    Math.floor(linhas / 2)
  ];

  const rotacionar = (lista, indice) =>
    lista.slice(indice).concat(lista.slice(0, indice));

  let indice = caminho.findIndex(
    ([x, y]) => x === inicio[0] && y === inicio[1]
  );

  if (indice < 0) {
    throw new Error("Posição inicial não encontrada no ciclo");
  }

  let ordenado = rotacionar(caminho, indice);

  // A cobra começa olhando para a direita.
  // O primeiro movimento do ciclo também deve ser para a direita.
  if (
    ordenado[1][0] !== inicio[0] + 1 ||
    ordenado[1][1] !== inicio[1]
  ) {
    ordenado = caminho.slice().reverse();
    indice = ordenado.findIndex(
      ([x, y]) => x === inicio[0] && y === inicio[1]
    );
    ordenado = rotacionar(ordenado, indice);
  }

  if (
    ordenado[1][0] !== inicio[0] + 1 ||
    ordenado[1][1] !== inicio[1]
  ) {
    throw new Error("Não foi possível orientar o ciclo para a direita");
  }

  const proximos = new Map();

  for (let i = 0; i < ordenado.length; i++) {
    const atual = ordenado[i];
    const proxima = ordenado[(i + 1) % ordenado.length];

    proximos.set(`${atual[0]},${atual[1]}`, proxima);
  }

  CACHE_CICLOS_HAMILTONIANOS.set(chave, proximos);
  return proximos;
}


// Busca um caminho entre a cabeça e um alvo, evitando o corpo.
// A cauda é considerada transitável porque normalmente se movimenta.
function buscarCaminho(est, corpo, alvo) {
  if (!corpo.length || !alvo) return null;

  const chave = ([x, y]) => `${x},${y}`;
  const inicio = corpo[0];
  const destino = chave(alvo);

  if (chave(inicio) === destino) return [];

  const bloqueadas = new Set(
    corpo.slice(1, -1).map(chave)
  );

  const fila = [inicio];
  const visitadas = new Set([chave(inicio)]);
  const anterior = new Map();

  const movimentos = [
    [1, 0], [-1, 0], [0, 1], [0, -1]
  ];

  let encontrou = false;

  for (let i = 0; i < fila.length; i++) {
    const atual = fila[i];

    for (const [dx, dy] of movimentos) {
      const proxima = [atual[0] + dx, atual[1] + dy];
      const k = chave(proxima);

      if (
        proxima[0] < 0 || proxima[0] >= est.cols ||
        proxima[1] < 0 || proxima[1] >= est.linhas ||
        visitadas.has(k) ||
        (bloqueadas.has(k) && k !== destino)
      ) {
        continue;
      }

      visitadas.add(k);
      anterior.set(k, chave(atual));

      if (k === destino) {
        encontrou = true;
        break;
      }

      fila.push(proxima);
    }

    if (encontrou) break;
  }

  if (!encontrou) return null;

  const caminho = [];
  let atual = destino;

  while (atual !== chave(inicio)) {
    const [x, y] = atual.split(",").map(Number);
    caminho.push([x, y]);
    atual = anterior.get(atual);
  }

  caminho.reverse();
  return caminho;
}

// Simula um caminho até a fruta e verifica se a cobra ainda
// consegue alcançar a cauda depois de comer.
function caminhoAteFrutaSeguro(est, caminho) {
  if (!caminho || caminho.length === 0) return false;

  const corpo = est.cobra.map(p => [...p]);
  const fruta = est.fruta;

  for (const proxima of caminho) {
    const comeu =
      fruta &&
      proxima[0] === fruta[0] &&
      proxima[1] === fruta[1];

    const limite = comeu ? corpo.length : corpo.length - 1;

    for (let i = 0; i < limite; i++) {
      if (
        corpo[i][0] === proxima[0] &&
        corpo[i][1] === proxima[1]
      ) {
        return false;
      }
    }

    corpo.unshift([...proxima]);

    if (!comeu) corpo.pop();
  }

  const cauda = corpo[corpo.length - 1];
  const estadoSimulado = {
    cols: est.cols,
    linhas: est.linhas
  };

  return buscarCaminho(estadoSimulado, corpo, cauda) !== null;
}

// Mede quantas casas livres continuam acessíveis.
function medirEspaco(corpo, cols, linhas) {
  const chave = ([x, y]) => `${x},${y}`;
  const bloqueadas = new Set(corpo.slice(1).map(chave));
  const fila = [corpo[0]];
  const visitadas = new Set([chave(corpo[0])]);

  const movimentos = [
    [1, 0], [-1, 0], [0, 1], [0, -1]
  ];

  for (let i = 0; i < fila.length; i++) {
    const [x, y] = fila[i];

    for (const [dx, dy] of movimentos) {
      const proxima = [x + dx, y + dy];
      const k = chave(proxima);

      if (
        proxima[0] < 0 || proxima[0] >= cols ||
        proxima[1] < 0 || proxima[1] >= linhas ||
        visitadas.has(k) ||
        bloqueadas.has(k)
      ) {
        continue;
      }

      visitadas.add(k);
      fila.push(proxima);
    }
  }

  return visitadas.size;
}

// Estratégia do vencedor: buscar fruta, preservar espaço e
// usar a cauda como destino alternativo quando necessário.
function decidirVencedorSeguro(est) {
  const corpo = est.cobra;
  const cabeca = corpo[0];

  if (est.fruta) {
    const caminhoFruta = buscarCaminho(
      est, corpo, est.fruta
    );

    if (
      caminhoFruta &&
      caminhoAteFrutaSeguro(est, caminhoFruta)
    ) {
      const p = caminhoFruta[0];
      return nomeDe([p[0] - cabeca[0], p[1] - cabeca[1]]);
    }
  }

  // Se não houver caminho seguro até a fruta, tenta acompanhar a cauda.
  const cauda = corpo[corpo.length - 1];
  const caminhoCauda = buscarCaminho(est, corpo, cauda);

  if (caminhoCauda && caminhoCauda.length > 0) {
    const p = caminhoCauda[0];
    return nomeDe([p[0] - cabeca[0], p[1] - cabeca[1]]);
  }

  // Último recurso: escolher a jogada legal que deixa mais espaço.
  const movimentos = [
    [1, 0], [-1, 0], [0, 1], [0, -1]
  ];

  let melhor = null;
  let melhorEspaco = -1;
  let melhorDistancia = Infinity;

  for (const [dx, dy] of movimentos) {
    const proxima = [cabeca[0] + dx, cabeca[1] + dy];

    if (
      proxima[0] < 0 || proxima[0] >= est.cols ||
      proxima[1] < 0 || proxima[1] >= est.linhas
    ) {
      continue;
    }

    const comeu =
      est.fruta &&
      proxima[0] === est.fruta[0] &&
      proxima[1] === est.fruta[1];

    const limite = comeu ? corpo.length : corpo.length - 1;
    let colisao = false;

    for (let i = 0; i < limite; i++) {
      if (
        corpo[i][0] === proxima[0] &&
        corpo[i][1] === proxima[1]
      ) {
        colisao = true;
        break;
      }
    }

    if (colisao) continue;

    const novoCorpo = [
      [...proxima],
      ...corpo.map(p => [...p])
    ];

    if (!comeu) novoCorpo.pop();

    const espaco = medirEspaco(
      novoCorpo, est.cols, est.linhas
    );

    const distancia = est.fruta
      ? Math.abs(proxima[0] - est.fruta[0]) +
        Math.abs(proxima[1] - est.fruta[1])
      : 0;

    if (
      espaco > melhorEspaco ||
      (espaco === melhorEspaco && distancia < melhorDistancia)
    ) {
      melhor = [dx, dy];
      melhorEspaco = espaco;
      melhorDistancia = distancia;
    }
  }

  if (melhor) return nomeDe(melhor);

  // Sem jogada segura disponível.
  return nomeDe([1, 0]);
}

export function decidirIA(modelo, est) {
  // O vencedor agora procura frutas por caminhos seguros.
  if (modelo.tipo === "ciclo_hamiltoniano") {
    return decidirVencedorSeguro(est);
  }

  // Os outros modelos continuam usando Random Forest.
  const f = features(est);

  return absolutoDe(
    preverAcao(modelo, paraRelativo(f, est.dirPasso)),
    est.dirPasso
  );
}
