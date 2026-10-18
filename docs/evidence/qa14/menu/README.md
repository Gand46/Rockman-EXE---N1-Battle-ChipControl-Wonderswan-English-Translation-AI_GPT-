# MANT05: PET, carrusel y SORT

Esta evidencia corresponde a las correcciones de `scripts/qa14_menu.py`, aplicadas sobre el inglés QA09 MANT04 exacto. El ejecutable combinado que se observó es `b9a16b3df0d3a2debc151d5dac8424bd70b262400b78f620c0767b9f8094be0f`. Las pruebas aquí descritas parten de SRAM fría y de estados generados por ese mismo ejecutable; las trazas no inyectan valores en WRAM.

## Hallazgos y lectura visual

| Soporte | Corrección | Comprobación |
|---|---|---|
| **Fuentes_Diferentes_PET** | SHOP, FREE BATTLE, HOST TOURNEY y BATTLE CHIP GP usan literalmente los capitales nativos que forman PET. Celda 8×16, cara máxima 7×11, avance 8; cara en y11..21. | P/E/T coinciden con ambas mitades de sus tiles originales. Se observaron los cinco destinos del carrusel a 224×144 y sus bandas a 3×, sin suavizado. No se modificó la fuente global. |
| **FuentesDiferentes_NAME,ATK,TYPE** | Cara de 6px de alto; P reutilizada de SP, siete letras adicionales dibujadas con las métricas y astas de la familia original. NAME empieza en x36, ATK en x70 y TYPE en x184. N ocupa 6px para conservar sus dos astas de 2px y una diagonal legible. | Se midieron 96 frames de cada una de las siete opciones y se compararon en la misma fase de la oscilación del selector. Las siete presentan 1px entre el extremo verde del puntero y el primer píxel de cara. ID y HP ya cumplen la misma relación que SP y CS y se conservaron. |
| **Menu_Desalineado** | Se recuperó la máscara completa de cada rótulo heredado de QA09 y se desplazó exactamente 4px hacia abajo, con separación de 24px. Se incluyeron la k terminal de Program Deck y los píxeles finales de Data Library, NetNavi y Save que MANT04 había dejado fuera de sus ventanas. | Las cinco caras empiezan en y20/44/68/92/116, como el selector. Se observaron las cinco selecciones y tres regresos al menú; ninguna letra queda elevada o cortada. Se conserva la forma, color y sombra de los rótulos heredados. |

La lectura directa confirma que los textos reconstruidos son legibles, mantienen la línea base y caben en sus campos. En SORT se conserva la animación nativa del puntero y su relación con SP/CS; no se mueve su código ni se intercambian acciones. Las comprobaciones de funcionamiento y las dos variantes integradas se relacionan en el informe general de QA14.

### Comparaciones

Las imágenes individuales de `screenshots/` mantienen **224×144**. Las hojas siguientes se forman mediante recorte y ampliación entera con vecino más próximo; no alteran el contenido de los píxeles:

- [Carrusel: MANT04 y MANT05 a 3×](screenshots/native_banners_before_after_3x.png).
- [Cinco rótulos completos: antes y después a 3×](screenshots/root_before_after_3x.png).
- [Las siete selecciones SORT en la misma fase a 4×](screenshots/sort_seven_selectors_4x.png).
- [SORT antes, resolución nativa](screenshots/sort_before_MANT04.png) y [después, resolución nativa](screenshots/sort_after_MANT05.png).

Los primeros archivos de captura MANT04 tenían permutados los alias `free`, `host` y `gp`. `banner_image_provenance.json` los relaciona con **el texto y destino que realmente muestran**; no se atribuye a una pantalla la captura de otra.

## Por qué se reubicó el banco PET

La corrección completa +4px requiere 70 patrones distintos; el banco anterior sólo ofrecía 55 ranuras seguras. El desplazamiento +6px de MANT04 permitía ahorrar patrones, pero no respetaba la alineación solicitada y además truncaba las ventanas de las palabras largas. Probar otras fases horizontales no proporcionó capacidad suficiente. Se mantuvo el selector nativo y se amplió el recurso gráfico.

El descriptor original en ROM `0x0700C0` es `25 0c c0 09 00 42 00 01`. Su cargador suma el primer campo, expresado en párrafos, al segmento del descriptor y conserva el offset; el segundo campo cuenta bytes. Por tanto, carga `7C25:00C0` = ROM `0x07C310`, longitud `0x09C0`, en VRAM `0x8000`. El nuevo descriptor es `f4 66 c0 0b 00 42 00 01`: ROM `0x0D7000`, longitud `0x0BC0`, mismo destino y mismos indicadores. Añade 16 tiles y deja el atlas antiguo intacto.

**ROM:** se decodificaron los 160 descriptores de la familia gráfica `0x070000..0x0704FF`. Ninguno alcanza el nuevo tramo `0x0D7000..0x0D7BBF`; el último final declarado es `0x0D6898`. La preimagen del tramo coincide con la ROM japonesa y con MANT04, por lo que no sustituye una aportación anterior. `rom_resource_directory.json` conserva el catálogo y sus hashes. La decisión no se basa en buscar relleno FF ni en suponer que los bytes sean cero.

**VRAM:** el espacio adicional `0x89C0..0x8BBF` contiene gráficos residuales del carrusel en MANT04. En las cinco selecciones originales no hay referencias a esos tiles en los cuatro mapas completos ni en las dos tablas de sprites examinadas. La nueva ruta fría de 2.526 frames confirma cuatro cargas PET: cada una escribe los 512 bytes adicionales una sola vez y siempre desde el cargador nativo `205C:005B`. Entre las cinco selecciones se registran **cero escrituras** a esa extensión. El carrusel y NetNavi reutilizan legítimamente el área al salir; cada regreso al PET vuelve a cargar el recurso correcto. Los ocho checkpoints del menú tienen **todo** VRAM `0x8000..0x8BBF` idéntico al atlas final en ROM.

`pet_loader_metrics.json` contiene los intervalos, hashes y resultados. `pet_loader_write_trace.patch` sólo añade observación con `fprintf` a una copia aislada del núcleo; no cambia ROM, RAM ni entradas. El núcleo observado tiene SHA-256 `fb62c4ff87a3bb59913fb397635d7356e359e32e491f9f478480d1165056f690`. El parche de observación y la ruta se conservan junto con el log sin resumir.

## Fuentes, guardas y reproducción

`apply(original_jp, mant04_english)` recibe la revisión japonesa de 4 MiB y el inglés MANT04, comprueba sus SHA-256 completos y 18 tramos de preimagen, y devuelve el resultado más los offsets modificados. El integrador combina esos offsets con los otros módulos a partir de **la misma** base MANT04 y recalcula el checksum final. El candidato de menú aislado tiene SHA-256 `3cac8494efefd727089387a401bb7da89873bdced3fde3c6065674cec3b3d0b4`; no debe confundirse con el ejecutable combinado observado arriba.

Las fuentes editables están en `components/qa09/translation/qa14_menu/`: máscaras completas heredadas para las cinco etiquetas, extensión de SORT en filas de píxeles y precondiciones. El carrusel lee los glifos del original suministrado durante la compilación. No depende de una ROM antigua oculta para reconstruir las máscaras de las etiquetas. La asignación de tiles verifica todos los consumidores estáticos fuera de los campos y respeta las banderas de reflejo horizontal/vertical. Los trece tiles de SORT se auditan en sus cuatro mapas compartidos.

Para reproducir una observación de escritura, se aplica el parche diagnóstico al núcleo externo indicado, se compila en una carpeta aislada y se ejecuta `qa14_capture_ui.capture` con `pet_loader_route.json` y la SRAM semilla cuyo hash figura en `pet_loader_capture.json`. Se fija `PYTHONUNBUFFERED=1` para conservar el orden entre registros del núcleo y checkpoints. `sort_frame_probe.patch` añade únicamente lecturas por frame de la imagen y de los dos buffers OAM al capturador; la ruta `sort_idle96_route.json` permite repetir la medición de fase.

El catálogo acredita los recursos gráficos declarados; la traza acredita las rutas ejecutadas. No se presenta ninguno como prueba de todos los posibles caminos de progresión ni de hardware físico. No queda un bloqueo para estas tres correcciones; la validación de Chip Control y las acciones concretas de cada pantalla corresponden al informe de integración.
