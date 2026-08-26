import json
import math
import re
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone


class RoteirizacaoError(Exception):
    pass


def _km(metros):
    return (Decimal(str(metros)) / Decimal("1000")).quantize(Decimal("0.01"))


def _minutos(segundos):
    return int(math.ceil(float(segundos) / 60)) if segundos else 0


def _http_json(url):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.ROTA_MOTOBOY_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=settings.ROTA_MOTOBOY_REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as erro:
        raise RoteirizacaoError(f"Servico de mapas respondeu com erro HTTP {erro.code}.") from erro
    except URLError as erro:
        raise RoteirizacaoError(f"Nao foi possivel acessar o servico de mapas: {erro.reason}.") from erro
    except TimeoutError as erro:
        raise RoteirizacaoError("O servico de mapas demorou para responder.") from erro
    except (ValueError, json.JSONDecodeError) as erro:
        raise RoteirizacaoError("O servico de mapas retornou uma resposta invalida.") from erro


def _endereco_para_busca(endereco):
    endereco = (endereco or "").strip()
    complemento = settings.ROTA_MOTOBOY_COMPLEMENTO_ENDERECO.strip()
    if complemento and complemento.lower() not in endereco.lower():
        return f"{endereco}, {complemento}"
    return endereco


def _normalizar_espacos(texto):
    return " ".join(str(texto or "").split())


def _sem_duplicar(valores):
    vistos = set()
    unicos = []
    for valor in valores:
        valor = _normalizar_espacos(valor)
        chave = valor.casefold()
        if not valor or chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(valor)
    return unicos


def _logradouro_numero(endereco):
    endereco = _normalizar_espacos(endereco)
    padroes = [
        r"^(?P<logradouro>.+?),\s*(?P<numero>\d+[A-Za-z]?)\b(?P<resto>.*)$",
        r"^(?P<logradouro>.+?)\s+(?P<numero>\d+[A-Za-z]?)\b(?P<resto>.*)$",
    ]
    for padrao in padroes:
        resultado = re.match(padrao, endereco)
        if resultado:
            return (
                resultado.group("logradouro").strip(" ,"),
                resultado.group("numero").strip(),
                resultado.group("resto").strip(" ,"),
            )
    return "", "", ""


def _parametros_geocoder(limite, **extras):
    params = {
        "format": "json",
        "limit": limite,
        "addressdetails": 1,
    }
    countrycodes = getattr(settings, "ROTA_MOTOBOY_COUNTRYCODES", "").strip()
    if countrycodes:
        params["countrycodes"] = countrycodes
    params.update({chave: valor for chave, valor in extras.items() if valor})
    return params


def _endereco_variantes_busca(endereco):
    endereco = _normalizar_espacos(endereco)
    endereco_com_complemento = _endereco_para_busca(endereco)
    logradouro, numero, resto = _logradouro_numero(endereco)
    variantes = [endereco_com_complemento, endereco]

    if logradouro and numero:
        partes_contexto = [
            resto,
            getattr(settings, "ROTA_MOTOBOY_CIDADE_PADRAO", ""),
            getattr(settings, "ROTA_MOTOBOY_ESTADO_PADRAO", ""),
            getattr(settings, "ROTA_MOTOBOY_PAIS_PADRAO", ""),
            settings.ROTA_MOTOBOY_COMPLEMENTO_ENDERECO,
        ]
        contexto = ", ".join(parte.strip(" ,") for parte in partes_contexto if str(parte or "").strip())
        variantes.extend(
            [
                f"{numero} {logradouro}, {contexto}" if contexto else f"{numero} {logradouro}",
                f"{logradouro} {numero}, {contexto}" if contexto else f"{logradouro} {numero}",
                f"{logradouro}, {contexto}" if contexto else logradouro,
            ]
        )

    return _sem_duplicar(variantes)


def _buscar_geocoder_por_texto(termo, limite):
    params = urlencode(_parametros_geocoder(limite, q=termo))
    url = f"{settings.ROTA_MOTOBOY_GEOCODER_URL}?{params}"
    return _http_json(url)


def _buscar_geocoder_estruturado(endereco, limite):
    logradouro, numero, _resto = _logradouro_numero(endereco)
    if not (logradouro and numero):
        return []

    params = _parametros_geocoder(
        limite,
        street=f"{numero} {logradouro}",
        city=getattr(settings, "ROTA_MOTOBOY_CIDADE_PADRAO", ""),
        state=getattr(settings, "ROTA_MOTOBOY_ESTADO_PADRAO", ""),
        country=getattr(settings, "ROTA_MOTOBOY_PAIS_PADRAO", ""),
    )
    if "city" not in params and "state" not in params and "country" not in params:
        return []

    url = f"{settings.ROTA_MOTOBOY_GEOCODER_URL}?{urlencode(params)}"
    return _http_json(url)


def geocodificar_endereco(endereco):
    endereco = _normalizar_espacos(endereco)
    if not endereco:
        raise RoteirizacaoError("Informe o endereco para calcular a rota.")

    consultas = [_buscar_geocoder_estruturado(endereco, 1)]
    consultas.extend(_buscar_geocoder_por_texto(termo, 1) for termo in _endereco_variantes_busca(endereco))

    dados = []
    for consulta in consultas:
        if consulta:
            dados = consulta
            break

    if not dados:
        raise RoteirizacaoError(f"Nao encontramos coordenadas para: {endereco}.")

    resultado = dados[0]
    return {
        "latitude": Decimal(str(resultado["lat"])).quantize(Decimal("0.000001")),
        "longitude": Decimal(str(resultado["lon"])).quantize(Decimal("0.000001")),
    }


def buscar_sugestoes_endereco(termo, limite=5):
    termo = _normalizar_espacos(termo)
    if len(termo) < 3:
        return []

    consultas = [_buscar_geocoder_estruturado(termo, limite)]
    consultas.extend(_buscar_geocoder_por_texto(termo_busca, limite) for termo_busca in _endereco_variantes_busca(termo))
    sugestoes = []
    nomes_vistos = set()
    for dados in consultas:
        for item in dados:
            nome = item.get("display_name")
            lat = item.get("lat")
            lon = item.get("lon")
            if not (nome and lat and lon) or nome in nomes_vistos:
                continue
            sugestoes.append({"nome": nome, "latitude": lat, "longitude": lon})
            nomes_vistos.add(nome)
            if len(sugestoes) >= limite:
                return sugestoes
    return sugestoes


def _coordenada_para_url(ponto):
    return f"{ponto['longitude']:.6f},{ponto['latitude']:.6f}"


def obter_viagem_otimizada(pontos, destino_fixo=True):
    coordenadas = ";".join(_coordenada_para_url(ponto) for ponto in pontos)
    params = urlencode(
        {
            "source": "first",
            "destination": "last" if destino_fixo else "any",
            "roundtrip": "false",
            "overview": "false",
            "steps": "false",
        }
    )
    url = f"{settings.ROTA_MOTOBOY_ROUTER_URL.rstrip('/')}/trip/v1/driving/{coordenadas}?{params}"
    dados = _http_json(url)
    if dados.get("code") != "Ok" or not dados.get("trips"):
        mensagem = dados.get("message") or "Nao foi possivel calcular a melhor rota."
        raise RoteirizacaoError(mensagem)
    return dados


def _coordenadas_ponto(endereco, latitude, longitude):
    if latitude is not None and longitude is not None:
        return {"latitude": latitude, "longitude": longitude}
    return geocodificar_endereco(endereco)


def _montar_pontos(rota, paradas):
    pontos = []
    tem_origem = bool(rota.endereco_inicio.strip())
    tem_destino = bool(rota.endereco_destino.strip())

    if tem_origem:
        origem = _coordenadas_ponto(rota.endereco_inicio, rota.latitude_inicio, rota.longitude_inicio)
        rota.latitude_inicio = origem["latitude"]
        rota.longitude_inicio = origem["longitude"]
        pontos.append(
            {
                "tipo": "origem",
                "parada": None,
                "input_index": 0,
                "latitude": rota.latitude_inicio,
                "longitude": rota.longitude_inicio,
            }
        )

    for parada in paradas:
        coordenadas = _coordenadas_ponto(parada.endereco, parada.latitude, parada.longitude)
        parada.latitude = coordenadas["latitude"]
        parada.longitude = coordenadas["longitude"]
        pontos.append(
            {
                "tipo": "parada",
                "parada": parada,
                "input_index": len(pontos),
                "latitude": parada.latitude,
                "longitude": parada.longitude,
            }
        )

    if tem_destino:
        destino = _coordenadas_ponto(
            rota.endereco_destino,
            rota.latitude_destino,
            rota.longitude_destino,
        )
        rota.latitude_destino = destino["latitude"]
        rota.longitude_destino = destino["longitude"]
        pontos.append(
            {
                "tipo": "destino",
                "parada": None,
                "input_index": len(pontos),
                "latitude": rota.latitude_destino,
                "longitude": rota.longitude_destino,
            }
        )

    return pontos, tem_origem


def _aplicar_viagem(rota, pontos, tem_origem, viagem):
    trip = viagem["trips"][0]
    legs = trip.get("legs", [])
    waypoint_indices = {
        indice: int(waypoint.get("waypoint_index", indice))
        for indice, waypoint in enumerate(viagem.get("waypoints", []))
    }
    pontos_paradas = [ponto for ponto in pontos if ponto["tipo"] == "parada"]
    pontos_paradas.sort(key=lambda ponto: waypoint_indices.get(ponto["input_index"], ponto["input_index"]))

    for posicao, ponto in enumerate(pontos_paradas, start=1):
        parada = ponto["parada"]
        parada.ordem = posicao
        parada.latitude = ponto["latitude"]
        parada.longitude = ponto["longitude"]

        if tem_origem:
            leg_index = posicao - 1
        else:
            leg_index = posicao - 2

        if 0 <= leg_index < len(legs):
            leg = legs[leg_index]
            parada.distancia_km = _km(leg.get("distance", 0))
            parada.duracao_minutos = _minutos(leg.get("duration", 0))
        else:
            parada.distancia_km = Decimal("0.00")
            parada.duracao_minutos = 0

        parada.save(
            update_fields=[
                "ordem",
                "latitude",
                "longitude",
                "distancia_km",
                "duracao_minutos",
            ]
        )

    rota.distancia_total_km = _km(trip.get("distance", 0))
    rota.duracao_total_minutos = _minutos(trip.get("duration", 0))
    rota.rota_otimizada_em = timezone.now()
    rota.save(
        update_fields=[
            "latitude_inicio",
            "longitude_inicio",
            "latitude_destino",
            "longitude_destino",
            "distancia_total_km",
            "duracao_total_minutos",
            "rota_otimizada_em",
            "atualizado_em",
        ]
    )


def _zerar_rota_unica(rota, paradas):
    for parada in paradas:
        parada.ordem = 1
        parada.distancia_km = Decimal("0.00")
        parada.duracao_minutos = 0
        parada.save(
            update_fields=[
                "ordem",
                "latitude",
                "longitude",
                "distancia_km",
                "duracao_minutos",
            ]
        )

    rota.distancia_total_km = Decimal("0.00")
    rota.duracao_total_minutos = 0
    rota.rota_otimizada_em = timezone.now()
    rota.save(
        update_fields=[
            "distancia_total_km",
            "duracao_total_minutos",
            "rota_otimizada_em",
            "atualizado_em",
        ]
    )


def otimizar_rota_motoboy(rota):
    paradas = list(rota.paradas.exclude(endereco="").order_by("ordem", "id"))
    if not paradas:
        raise RoteirizacaoError("Cadastre ao menos uma parada com endereco.")

    with transaction.atomic():
        pontos, tem_origem = _montar_pontos(rota, paradas)
        if len(pontos) < 2:
            _zerar_rota_unica(rota, paradas)
            return rota

        viagem = obter_viagem_otimizada(pontos, destino_fixo=bool(rota.endereco_destino.strip()))
        _aplicar_viagem(rota, pontos, tem_origem, viagem)

    rota.refresh_from_db()
    return rota
