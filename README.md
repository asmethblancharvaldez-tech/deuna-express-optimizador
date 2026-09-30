# DeUna Express — Planificador web de rutas

Prototipo académico desarrollado para el trabajo de grado sobre optimización del proceso de distribución de última milla de DeUna Express.

## Modelo implementado
La aplicación trata cada bloque de pedidos como una instancia estática de un **Problema de Ruteo de Vehículos con Capacidad (CVRP)** y genera las rutas mediante la **heurística de ahorros de Clarke & Wright**.

## Flujo
1. El usuario define el lote y el bloque operativo.
2. Registra la dirección del depósito.
3. Indica las motocicletas disponibles y la capacidad de cada una.
4. Registra clientes, direcciones y demanda.
5. La aplicación geocodifica las direcciones.
6. Construye automáticamente la matriz de distancias y tiempos por red vial.
7. Aplica Clarke & Wright respetando las capacidades.
8. Presenta la secuencia de cada ruta, distancia, tiempo estimado, carga y enlace cartográfico.

## Criterio
El criterio principal es la **menor distancia total recorrida**, en coherencia con la formulación y evaluación económica del trabajo de grado.

## Alcance
El prototipo está diseñado para trabajar por lotes (batching), permitiendo que el número de clientes y de motocicletas cambie entre ejecuciones.
