# Rockman EXE N1 Battle — Localización inglesa MANT05

Versión vigente **QA09 MANT05**, reconstruida sobre MANT04 y la traducción
acumulativa. Hay dos BPS independientes: inglés e **inglés + Chip Control RC6
experimental**. Cada uno se aplica directamente a la ROM japonesa Rev. 1.

## Correcciones

| Soporte | Resultado |
| --- | --- |
| Fuente_Diferente_SHOP | `1 CHIP`, `10 CHIPS` e `INFO` usan celdas nativas 8×16, contrastadas con las cifras originales de la tienda. Se mantienen los precios y las acciones. |
| Fuentes_Diferentes_PET | SHOP, BATTLE CHIP GP, FREE BATTLE y HOST TOURNEY emplean la familia original de PET: caras de 7×11, avance de 8 píxeles y línea base común. |
| FuentesDiferentes_NAME,ATK,TYPE | Fuente pequeña de seis píxeles: P literal y extensiones documentadas. Los siete rótulos se contrastan con el ciclo completo del puntero. |
| Menu_Desalineado | Cinco rótulos completos bajan cuatro píxeles desde sus máscaras QA09. Un banco ampliado evita recortar Program Deck/Data Library y conserva el selector. |
| Total Chips Numero Artefactos | Eran sufijos T/C legítimos deformados. Se reconstruyen con glifos nativos completos; permanecen el contador y el adorno naranja original. |

El [informe visual](reports/qa14-native-ui.html) compara soporte, original, MANT04
y MANT05 a resolución nativa y con zoom sin suavizado. Una compra real cambia
9 T / 13 C a 9 T / 14 C; persiste al reentrar, guardar y arrancar en frío.
Los [datos técnicos](qa14-native-ui.md) explican la reubicación y sus guardas.

## Reconstruir

```sh
python scripts/project.py build --source /ruta/ROM_original.wsc --variant all
python scripts/project.py verify --source /ruta/ROM_original.wsc
```

ROM base: 4.194.304 bytes, SHA-256
`4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed`.
Resultados en `build/mant05/`. No hacen falta una ROM traducida ni un paquete
anterior para compilar. El archivo original permanece intacto.

Las fuentes incluyen traducción, recursos, scripts nuevos/heredados, pruebas,
informes, dos BPS e inventarios. Partidas, ROMs y emulador compilado quedan fuera.

**Alcance:** lectura visual y navegación de pantallas afectadas; 53 capturas por
variante; regresión en dos combates sintéticos con 32 checkpoints por variante.
No se ha probado hardware físico ni todas las combinaciones de juego.

**Pendiente heredado concreto:** faltan el ensamblador y constructor originales
RC6. El adaptador y las correcciones nuevas sí son editables. Chip Control conserva
su condición experimental.
