"""
ventana_config.py - Ventana de configuración (Tkinter) para cada colega.

Permite:
  - Registrar usuario (CUIL) y contraseña del PJN.
  - "Probar login": valida contra el portal real y guarda la sesión en profile/.
  - Elegir la hora de corrida (martes y viernes).
  - "Guardar y agendar": guarda credenciales en el almacén seguro y crea la
    tarea del Programador de Windows.
  - "Correr ahora": dispara una corrida visible a demanda (para probar).

Las operaciones lentas (probar login, correr) se ejecutan fuera del hilo de la
interfaz para que la ventana no se congele:
  - "Probar login" corre en un hilo y devuelve el resultado por una cola.
  - "Correr ahora" se lanza como proceso aparte (consola propia con el log).
"""
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

import acerca
import agendar
import credenciales
import navegador
import rutas
import sesion

HORA_POR_DEFECTO = "09:00"


def abrir():
    """Abre la ventana de configuración (bloquea hasta que se cierra)."""
    _App().mainloop()


def _comando_app(*flags):
    """Comando (lista para subprocess) que re-lanza la app con `flags`."""
    if rutas.esta_congelado():
        return [sys.executable, *flags]
    main_py = Path(__file__).parent.parent / "main.py"
    return [sys.executable, str(main_py), *flags]


class _App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Scout PJN — Dejar notas")
        self.resizable(False, False)
        self._cola = queue.Queue()
        self._construir()
        self._cargar_valores()
        self.after(200, self._pump)         # atiende mensajes de hilos de fondo
        self.after(300, self._chequear_navegador)

    # --------------------------- construcción UI ---------------------------
    def _construir(self):
        pad = {"padx": 10, "pady": 6}
        marco = ttk.Frame(self, padding=14)
        marco.grid(sticky="nsew")

        ttk.Label(marco, text="Configuración de corridas automáticas",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 10))

        ttk.Label(marco, text="Usuario (CUIL):").grid(row=1, column=0, sticky="e", **pad)
        self.e_user = ttk.Entry(marco, width=28)
        self.e_user.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(marco, text="Contraseña:").grid(row=2, column=0, sticky="e", **pad)
        self.e_pwd = ttk.Entry(marco, width=28, show="•")
        self.e_pwd.grid(row=2, column=1, sticky="w", **pad)

        self.var_ver = tk.BooleanVar(value=False)
        ttk.Checkbutton(marco, text="ver contraseña", variable=self.var_ver,
                        command=self._toggle_pwd).grid(row=3, column=1, sticky="w", padx=10)

        ttk.Label(marco, text="Hora (HH:MM, martes y viernes):").grid(
            row=4, column=0, sticky="e", **pad)
        self.e_hora = ttk.Entry(marco, width=10)
        self.e_hora.grid(row=4, column=1, sticky="w", **pad)

        # Botones
        botones = ttk.Frame(marco)
        botones.grid(row=5, column=0, columnspan=2, pady=(10, 4))
        self.b_probar = ttk.Button(botones, text="Probar login", command=self._probar_login)
        self.b_probar.grid(row=0, column=0, padx=5)
        self.b_guardar = ttk.Button(botones, text="Guardar y agendar", command=self._guardar)
        self.b_guardar.grid(row=0, column=1, padx=5)
        self.b_simular = ttk.Button(botones, text="Simulacro (no deja notas)", command=self._simular)
        self.b_simular.grid(row=0, column=2, padx=5)
        self.b_correr = ttk.Button(botones, text="Correr ahora", command=self._correr_ahora)
        self.b_correr.grid(row=0, column=3, padx=5)

        # Estado / mensajes
        self.txt_estado = tk.Text(marco, width=52, height=5, wrap="word",
                                  state="disabled", relief="flat", background="#f4f4f4")
        self.txt_estado.grid(row=6, column=0, columnspan=2, pady=(8, 0))

        # Pie: descargar navegador + versión + "Acerca de..."
        pie = ttk.Frame(marco)
        pie.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.b_navegador = ttk.Button(pie, text="Descargar navegador",
                                      command=self._descargar_navegador)
        self.b_navegador.pack(side="left")
        ttk.Label(pie, text=f"v{acerca.APP_VERSION}", foreground="#666").pack(
            side="left", padx=10)
        ttk.Button(pie, text="Acerca de…", command=self._acerca).pack(side="right")

    def _cargar_valores(self):
        user = credenciales.usuario_configurado()
        if user:
            self.e_user.insert(0, user)
        self.e_hora.insert(0, credenciales.hora_configurada() or HORA_POR_DEFECTO)
        if credenciales.esta_configurado():
            estado_tarea = "y con tarea agendada" if agendar.existe() else "pero SIN tarea agendada"
            self._estado(f"App configurada para {user} {estado_tarea}.\n"
                         f"Podés reprobar el login, cambiar la hora o correr ahora.")
        else:
            self._estado("Primera configuración: completá usuario, contraseña y hora.\n"
                         "Probá el login (queda la sesión guardada) y luego 'Guardar y agendar'.")

    # ------------------------------ acciones -------------------------------
    def _toggle_pwd(self):
        self.e_pwd.config(show="" if self.var_ver.get() else "•")

    def _valores(self):
        return self.e_user.get().strip(), self.e_pwd.get(), self.e_hora.get().strip()

    def _probar_login(self):
        user, pwd, _ = self._valores()
        if not user or not pwd:
            messagebox.showwarning("Faltan datos", "Completá usuario y contraseña.")
            return
        if not self._requiere_navegador():
            return
        self._habilitar(False)
        self._estado("Probando login contra el portal del PJN...\n"
                     "Se abrirá una ventana del navegador. Si aparece un captcha o "
                     "segundo factor, resolvelo ahí.")

        def tarea():
            res = sesion.probar_login(user, pwd, headless=False)
            self._cola.put(("probar", res))

        threading.Thread(target=tarea, daemon=True).start()

    def _pump(self):
        """Atiende mensajes de los hilos de fondo (login, descarga) y actualiza
        la UI desde el hilo principal. Corre siempre mientras la ventana vive."""
        try:
            while True:
                tipo, dato = self._cola.get_nowait()
                self._despachar(tipo, dato)
        except queue.Empty:
            pass
        self.after(200, self._pump)

    def _despachar(self, tipo, dato):
        if tipo == "probar":
            self._habilitar(True)
            self._estado(dato["mensaje"])
            if dato["ok"]:
                # Login válido: guardamos la credencial ya, así no se pierde.
                user, _pwd, _ = self._valores()
                credenciales.guardar_credencial(user, self.e_pwd.get())
                cfg = credenciales.leer_config()
                cfg["pjn_user"] = user
                credenciales.guardar_config(cfg)
        elif tipo == "nav_linea":
            self._estado(f"Descargando el navegador (una sola vez)...\n{dato}")
        elif tipo == "nav_fin":
            ok, msg = dato
            self._habilitar(True)
            self._estado(msg)

    def _guardar(self):
        user, pwd, hora = self._valores()
        if not user or not pwd:
            messagebox.showwarning("Faltan datos", "Completá usuario y contraseña.")
            return
        if not agendar._validar_hora(hora):
            messagebox.showwarning("Hora inválida", "Usá el formato HH:MM (24 horas), ej. 09:30.")
            return
        credenciales.guardar_todo(user, pwd, hora)
        ok, msg = agendar.crear_o_actualizar(hora)
        if ok:
            self._estado("✅ Credenciales guardadas en el almacén seguro.\n" + msg)
            messagebox.showinfo("Listo", msg)
        else:
            self._estado("Credenciales guardadas, pero falló el agendado:\n" + msg)
            messagebox.showerror("Agendado", msg)

    def _correr_ahora(self):
        if not self._requiere_navegador():
            return
        if not credenciales.esta_configurado():
            resp = messagebox.askyesno(
                "Sin guardar",
                "Todavía no guardaste las credenciales. ¿Querés guardarlas y correr ahora?")
            if not resp:
                return
            self._guardar()
            if not credenciales.esta_configurado():
                return
        self._estado("Lanzando una corrida a demanda (visible). Mirá la ventana de consola "
                     "que se abre; el resultado queda en la carpeta de registros.")
        subprocess.Popen(_comando_app("--ahora"))

    def _simular(self):
        if not self._requiere_navegador():
            return
        if not credenciales.esta_configurado():
            messagebox.showwarning(
                "Sin configurar",
                "Primero probá el login (o guardá) para tener la sesión guardada.")
            return
        self._estado("Lanzando un SIMULACRO (visible, NO deja notas): el robot inicia sesión, "
                     "navega y verifica los expedientes, pero nunca confirma. Mirá la ventana "
                     "del navegador; el resultado queda en la carpeta de registros.")
        subprocess.Popen(_comando_app("--simulacro", "--ver"))

    # ---------------------------- navegador --------------------------------
    def _requiere_navegador(self) -> bool:
        """Si falta Chromium, avisa y frena la acción. True si está listo."""
        if navegador.chromium_instalado():
            return True
        messagebox.showinfo(
            "Falta el navegador",
            "Primero descargá el navegador con el botón 'Descargar navegador' "
            "(abajo a la izquierda). Es una sola vez.")
        return False

    def _chequear_navegador(self):
        """Al abrir: si falta Chromium, ofrece descargarlo."""
        if navegador.chromium_instalado():
            return
        if messagebox.askyesno(
                "Falta el navegador",
                "Para funcionar, la app necesita descargar el navegador (Chromium, "
                "~150 MB). Es una sola vez y queda guardado. ¿Descargar ahora?"):
            self._descargar_navegador()
        else:
            self._estado("⚠️ Falta el navegador. Usá 'Descargar navegador' antes de "
                         "probar el login o correr.")

    def _descargar_navegador(self):
        if navegador.chromium_instalado():
            self._estado("El navegador ya está instalado.")
            return
        self._habilitar(False)
        self._estado("Descargando el navegador (~150 MB). Puede tardar unos minutos...")

        def tarea():
            ok, msg = navegador.instalar_chromium(
                on_linea=lambda l: self._cola.put(("nav_linea", l)))
            self._cola.put(("nav_fin", (ok, msg)))

        threading.Thread(target=tarea, daemon=True).start()

    def _acerca(self):
        """Cartel 'Acerca de...' con el descargo y link al repositorio."""
        v = tk.Toplevel(self)
        v.title("Acerca de")
        v.resizable(False, False)
        v.transient(self)
        m = ttk.Frame(v, padding=16)
        m.grid(sticky="nsew")
        ttk.Label(m, text=acerca.APP_NOMBRE, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w")
        ttk.Label(m, text=f"Versión {acerca.APP_VERSION}", foreground="#666").grid(
            row=1, column=0, sticky="w", pady=(0, 8))
        cuerpo = tk.Message(m, text=acerca.DESCARGO, width=380, justify="left")
        cuerpo.grid(row=2, column=0, sticky="w")
        link = ttk.Label(m, text=acerca.REPO_URL, foreground="#1a5fb4", cursor="hand2")
        link.grid(row=3, column=0, sticky="w", pady=(10, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open(acerca.REPO_URL))
        ttk.Button(m, text="Cerrar", command=v.destroy).grid(
            row=4, column=0, sticky="e", pady=(14, 0))

    # ------------------------------ helpers UI -----------------------------
    def _habilitar(self, on):
        estado = "normal" if on else "disabled"
        for b in (self.b_probar, self.b_guardar, self.b_simular, self.b_correr,
                  self.b_navegador):
            b.config(state=estado)

    def _estado(self, msg):
        self.txt_estado.config(state="normal")
        self.txt_estado.delete("1.0", "end")
        self.txt_estado.insert("1.0", msg)
        self.txt_estado.config(state="disabled")
