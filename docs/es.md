# Guía del repositorio

**QA09/MANT03 sigue siendo la traducción principal. Chip Control RC6 es opcional y experimental.**
La versión 2.0 corresponde únicamente a la organización del repositorio, no a una nueva ROM.

La raíz contiene las instrucciones vigentes. El código y los recursos están en dos
componentes separados; `patches/qa09/` contiene el BPS normal y `patches/chip-control/`
el experimental. Aplica uno solo sobre el original japonés verificado; no encadenes
los parches y no utilices el IPS histórico directamente sobre QA09.

```console
python scripts/project.py build --source "ruta/al/original.wsc"
python scripts/project.py build --source "ruta/al/original.wsc" --variant all
python -m pip install -r requirements/qa.txt
python scripts/project.py verify --source "ruta/al/original.wsc"
```

La compilación predeterminada es QA09. Los resultados permanecen bajo `build/`, que
queda excluido de Git y del empaquetado. El constructor normal respeta el manifiesto
editable actual y no lo sobrescribe mediante composiciones históricas.

Los informes HTML completos están en [el índice de informes](reports/index.html).
Los documentos retirados, capturas históricas no necesarias para las pruebas actuales
y antiguas herramientas de empaquetado están en el ZIP histórico independiente.
**No hace falta ese ZIP para reconstruir ninguna de las dos variantes actuales.**
El registro `maintenance/migration.json` permite localizar cada archivo original y
comprobar que no se perdió material durante la limpieza.

[Cómo compilar](build.md) · [Cómo editar](editing.md) · [Qué se validó](validation.md)

Las fuentes del adaptador RC6 están presentes, pero faltan las fuentes ensamblador
originales de su motor en el material recibido. La autorización de redistribución de
su carga binaria tampoco está documentada. La reorganización no resuelve ni oculta
esas limitaciones. [Créditos y procedencia](provenance.md).
