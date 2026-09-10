#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sanger_gui.py — ventana para clasificar_sanger.py (sin terminal).

Permite elegir la carpeta con los .ab1, el mail para NCBI y las opciones más
usadas, y muestra el progreso en pantalla. Es un envoltorio: toda la lógica
sigue en clasificar_sanger.py, que tiene que estar en la misma carpeta.

Para construir el .exe de Windows, ver construir_exe.bat.
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# clasificar_sanger.py vive junto a este archivo (o dentro del .exe)
sys.path.insert(0, str(Path(getattr(sys, "_MEIPASS", Path(__file__).parent))))
import clasificar_sanger  # noqa: E402

BASES = ["nt", "core_nt", "mito", "16S_ribosomal_RNA", "ITS_RefSeq_Fungi",
         "ITS_eukaryote_sequences", "18S_fungal_sequences", "28S_fungal_sequences"]
TAXONES = ["(sin filtro)", "Vertebrata[Organism]", "Mammalia[Organism]", "Aves[Organism]",
           "Insecta[Organism]", "Bacteria[Organism]", "Fungi[Organism]", "Viridiplantae[Organism]"]


class Redirector:
    """Captura los print() del script y los manda a la ventana."""
    def __init__(self, cola):
        self.cola = cola
    def write(self, texto):
        if texto:
            self.cola.put(texto)
    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clasificador de secuencias Sanger")
        self.geometry("860x640")
        try:   # icono de la ventana (solo Windows; si no está, no pasa nada)
            _ico = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "logo_mosquito.ico"
            if _ico.exists():
                self.iconbitmap(str(_ico))
        except Exception:
            pass
        self.minsize(720, 520)
        self.cola = queue.Queue()
        self.hilo = None
        self._armar()
        self.after(100, self._vaciar_cola)

    # ---------------- interfaz ----------------
    def _armar(self):
        marco = ttk.Frame(self, padding=10)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(1, weight=1)

        fila = 0
        ttk.Label(marco, text="Carpeta con los .ab1:").grid(row=fila, column=0, sticky="w", pady=3)
        self.v_entrada = tk.StringVar()
        ttk.Entry(marco, textvariable=self.v_entrada).grid(row=fila, column=1, sticky="ew", padx=5)
        ttk.Button(marco, text="Elegir…", command=self._elegir_entrada).grid(row=fila, column=2)

        fila += 1
        ttk.Label(marco, text="Carpeta de resultados:").grid(row=fila, column=0, sticky="w", pady=3)
        self.v_salida = tk.StringVar()
        ttk.Entry(marco, textvariable=self.v_salida).grid(row=fila, column=1, sticky="ew", padx=5)
        ttk.Button(marco, text="Elegir…", command=self._elegir_salida).grid(row=fila, column=2)

        fila += 1
        ttk.Label(marco, text="E-mail (lo pide NCBI):").grid(row=fila, column=0, sticky="w", pady=3)
        self.v_email = tk.StringVar()
        ttk.Entry(marco, textvariable=self.v_email).grid(row=fila, column=1, sticky="ew", padx=5)

        fila += 1
        ttk.Label(marco, text="Base de datos:").grid(row=fila, column=0, sticky="w", pady=3)
        self.v_db = tk.StringVar(value="nt")
        ttk.Combobox(marco, textvariable=self.v_db, values=BASES, width=28).grid(row=fila, column=1, sticky="w", padx=5)

        fila += 1
        ttk.Label(marco, text="Restringir a (opcional):").grid(row=fila, column=0, sticky="w", pady=3)
        self.v_taxon = tk.StringVar(value=TAXONES[0])
        ttk.Combobox(marco, textvariable=self.v_taxon, values=TAXONES, width=28).grid(row=fila, column=1, sticky="w", padx=5)

        fila += 1
        opciones = ttk.LabelFrame(marco, text="Umbrales (los valores por defecto sirven para amplicones de 200–400 pb)", padding=8)
        opciones.grid(row=fila, column=0, columnspan=3, sticky="ew", pady=6)
        self.v_largo = tk.StringVar(value="100")
        self.v_largo_laxo = tk.StringVar(value="60")
        self.v_ident = tk.StringVar(value="97")
        self.v_lote = tk.StringVar(value="50")
        for i, (etq, var, ayuda) in enumerate([
                ("Largo mínimo CONFIABLE (pb)", self.v_largo, "300–400 para COI Folmer / 16S completo"),
                ("Largo mínimo DUDOSA (pb)", self.v_largo_laxo, "bajar a 50 para ver más casos límite"),
                ("% identidad para 'identificado'", self.v_ident, "98.7 para 16S bacteriano"),
                ("Secuencias por envío a NCBI", self.v_lote, "bajar a 20 si NCBI rechaza el lote")]):
            ttk.Label(opciones, text=etq + ":").grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(opciones, textvariable=var, width=8).grid(row=i, column=1, sticky="w", padx=6)
            ttk.Label(opciones, text=ayuda, foreground="gray").grid(row=i, column=2, sticky="w")
        self.v_noblast = tk.BooleanVar(value=False)
        ttk.Checkbutton(opciones, text="Solo control de calidad y clasificación (sin BLAST; es instantáneo)",
                        variable=self.v_noblast).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        fila += 1
        botones = ttk.Frame(marco)
        botones.grid(row=fila, column=0, columnspan=3, sticky="ew", pady=6)
        self.b_correr = ttk.Button(botones, text="Analizar", command=self._correr)
        self.b_correr.pack(side="left")
        self.b_abrir = ttk.Button(botones, text="Abrir carpeta de resultados", command=self._abrir_resultados, state="disabled")
        self.b_abrir.pack(side="left", padx=8)
        self.estado = ttk.Label(botones, text="")
        self.estado.pack(side="left", padx=10)

        fila += 1
        marco.rowconfigure(fila, weight=1)
        self.log = scrolledtext.ScrolledText(marco, wrap="none", font=("Consolas", 9), state="disabled")
        self.log.grid(row=fila, column=0, columnspan=3, sticky="nsew")

    def _elegir_entrada(self):
        d = filedialog.askdirectory(title="Carpeta con los cromatogramas .ab1")
        if d:
            self.v_entrada.set(d)
            if not self.v_salida.get():
                self.v_salida.set(str(Path(d) / "resultados"))

    def _elegir_salida(self):
        d = filedialog.askdirectory(title="Carpeta donde guardar los resultados")
        if d:
            self.v_salida.set(d)

    def _abrir_resultados(self):
        ruta = self.v_salida.get()
        if not ruta or not Path(ruta).exists():
            return
        if sys.platform.startswith("win"):
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])

    # ---------------- ejecución ----------------
    def _correr(self):
        entrada = self.v_entrada.get().strip()
        salida = self.v_salida.get().strip() or str(Path(entrada) / "resultados")
        if not entrada or not Path(entrada).is_dir():
            messagebox.showerror("Falta la carpeta", "Elegí la carpeta que contiene los archivos .ab1.")
            return
        if not self.v_noblast.get() and "@" not in self.v_email.get():
            messagebox.showerror("Falta el e-mail", "NCBI pide un e-mail para el BLAST remoto.\n"
                                 "Escribí uno, o marcá 'sin BLAST'.")
            return
        try:
            argv = ["clasificar_sanger.py", "-i", entrada, "-o", salida,
                    "--largo-min", str(int(self.v_largo.get())),
                    "--largo-min-laxo", str(int(self.v_largo_laxo.get())),
                    "--ident-min", str(float(self.v_ident.get())),
                    "--lote", str(int(self.v_lote.get())),
                    "--db", self.v_db.get().strip() or "nt"]
        except ValueError:
            messagebox.showerror("Valor inválido", "Los umbrales tienen que ser números.")
            return
        if self.v_noblast.get():
            argv.append("--no-blast")
        else:
            argv += ["--email", self.v_email.get().strip()]
        if self.v_taxon.get() and not self.v_taxon.get().startswith("("):
            argv += ["--taxon", self.v_taxon.get().strip()]

        self._log_limpiar()
        self._log("Comando equivalente:\n  python3 " + " ".join(argv) + "\n\n")
        self.b_correr.config(state="disabled")
        self.b_abrir.config(state="disabled")
        self.estado.config(text="Analizando… (el BLAST puede tardar varios minutos)")
        self.hilo = threading.Thread(target=self._trabajo, args=(argv,), daemon=True)
        self.hilo.start()

    def _trabajo(self, argv):
        viejo_out, viejo_err, viejo_argv = sys.stdout, sys.stderr, sys.argv
        sys.stdout = sys.stderr = Redirector(self.cola)
        sys.argv = argv
        try:
            clasificar_sanger.main()
            self.cola.put("\n__FIN_OK__")
        except SystemExit as e:
            self.cola.put(f"\n[El análisis se detuvo: {e}]\n__FIN_ERR__")
        except Exception as e:
            import traceback
            self.cola.put("\n[Error inesperado]\n" + traceback.format_exc() + "\n__FIN_ERR__")
        finally:
            sys.stdout, sys.stderr, sys.argv = viejo_out, viejo_err, viejo_argv

    def _vaciar_cola(self):
        try:
            while True:
                texto = self.cola.get_nowait()
                if texto.endswith("__FIN_OK__"):
                    self._log(texto.replace("__FIN_OK__", ""))
                    self.estado.config(text="Listo.")
                    self.b_correr.config(state="normal")
                    self.b_abrir.config(state="normal")
                elif texto.endswith("__FIN_ERR__"):
                    self._log(texto.replace("__FIN_ERR__", ""))
                    self.estado.config(text="Terminó con error (ver mensaje arriba).")
                    self.b_correr.config(state="normal")
                else:
                    self._log(texto)
        except queue.Empty:
            pass
        self.after(150, self._vaciar_cola)

    def _log(self, texto):
        self.log.config(state="normal")
        self.log.insert("end", texto)
        self.log.see("end")
        self.log.config(state="disabled")

    def _log_limpiar(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")


if __name__ == "__main__":
    App().mainloop()
