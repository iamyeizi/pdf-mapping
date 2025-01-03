import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from PIL import Image, ImageTk
import fitz  # PyMuPDF para manejar PDFs
import sqlite3


class InteractivePDFApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive PDF Viewer")

        # Variables para datos y el canvas
        self.pdf_files = {}
        self.current_file = None
        self.current_page = 0
        self.notes = {}
        self.pdf_document = None
        self.photo = None
        self.zoom_level = 1.0
        self.dragging_tag = None
        self.is_panning = False
        self.pan_start = (0, 0)
        self.edit_mode = True

        # Configurar la base de datos
        self.db_connection = sqlite3.connect("pdf_notes.db")
        self.db_cursor = self.db_connection.cursor()
        self.setup_database()

        # Configurar la interfaz
        self.canvas = tk.Canvas(root, bg="gray")
        self.canvas.pack(expand=True, fill=tk.BOTH)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<MouseWheel>", self.zoom_with_mouse)
        self.canvas.bind("<B1-Motion>", self.move_tag)
        self.canvas.bind("<ButtonRelease-1>", self.drop_tag)
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.pan)
        self.canvas.bind("<ButtonRelease-2>", self.end_pan)

        # Menú de navegación
        self.menu = tk.Menu(root)
        root.config(menu=self.menu)

        file_menu = tk.Menu(self.menu, tearoff=0)
        file_menu.add_command(label="Cargar PDF(s)", command=self.load_pdfs)
        file_menu.add_command(label="Guardar Notas",
                              command=self.save_notes_to_db)
        file_menu.add_command(label="Cargar Notas", command=self.load_notes)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=root.quit)
        self.menu.add_cascade(label="Archivo", menu=file_menu)

        navigate_menu = tk.Menu(self.menu, tearoff=0)
        navigate_menu.add_command(
            label="Página Siguiente", command=self.next_page)
        navigate_menu.add_command(
            label="Página Anterior", command=self.previous_page)
        navigate_menu.add_command(label="Acercar (+)", command=self.zoom_in)
        navigate_menu.add_command(label="Alejar (-)", command=self.zoom_out)
        self.menu.add_cascade(label="Navegación", menu=navigate_menu)

        mode_menu = tk.Menu(self.menu, tearoff=0)
        mode_menu.add_command(label="Modo Edición", command=self.set_edit_mode)
        mode_menu.add_command(label="Modo Vista", command=self.set_view_mode)
        self.menu.add_cascade(label="Modo", menu=mode_menu)

    def setup_database(self):
        self.db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY,
                file_name TEXT,
                page_num INTEGER,
                x REAL,
                y REAL,
                alias TEXT,
                note TEXT
            )
        """)
        self.db_connection.commit()

    def load_pdfs(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Archivos PDF", "*.pdf")])
        if not paths:
            return

        for path in paths:
            name = path.split("/")[-1]
            self.pdf_files[name] = path

        self.current_file = list(self.pdf_files.keys())[0]
        self.load_pdf(self.current_file)

    def load_pdf(self, file_name):
        self.pdf_document = fitz.open(self.pdf_files[file_name])
        self.current_file = file_name
        self.current_page = 0
        self.notes = self.load_notes_from_db()
        self.display_page()

    def display_page(self):
        if not self.pdf_document:
            return

        page = self.pdf_document[self.current_page]
        pix = page.get_pixmap(matrix=fitz.Matrix(
            self.zoom_level, self.zoom_level))
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.photo = ImageTk.PhotoImage(image)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))

        # Dibujar notas existentes en la página actual
        for (file_name, page_num, x, y), note in self.notes.items():
            if file_name == self.current_file and page_num == self.current_page:
                scaled_x, scaled_y = x * self.zoom_level, y * self.zoom_level
                tag_id = self.canvas.create_oval(
                    scaled_x - 5, scaled_y - 5, scaled_x + 5, scaled_y + 5, fill="red")
                alias_id = self.canvas.create_text(
                    scaled_x + 10, scaled_y, text=note["alias"], anchor=tk.W, fill="blue", font=("Arial", 10, "bold"))
                self.canvas.tag_bind(tag_id, "<Button-1>", lambda e, key=(
                    file_name, page_num, x, y): self.show_note_details(key))
                self.canvas.tag_bind(alias_id, "<Button-1>", lambda e, key=(
                    file_name, page_num, x, y): self.show_note_details(key))

    def on_click(self, event):
        if not self.edit_mode:
            return
        x, y = event.x / self.zoom_level, event.y / self.zoom_level
        alias = simpledialog.askstring(
            "Agregar Nota", "Escribe un alias para este punto:")
        if alias:
            note = simpledialog.askstring(
                "Agregar Nota", "Escribe la información para este punto:")
            if note:
                self.notes[(self.current_file, self.current_page, x, y)] = {
                    "alias": alias, "note": note}
                self.save_note_to_db(
                    self.current_file, self.current_page, x, y, alias, note)
                self.display_page()

    def show_note_details(self, key):
        note_data = self.notes.get(key)
        if note_data:
            response = messagebox.askyesnocancel("Nota", f"Alias: {note_data['alias']}\nNota: {
                                                 note_data['note']}\n\n¿Quieres modificar esta nota?")
            if response is True:
                new_note = simpledialog.askstring(
                    "Modificar Nota", "Escribe la nueva información:", initialvalue=note_data["note"])
                if new_note:
                    self.notes[key]["note"] = new_note
                    self.update_note_in_db(key, new_note)
            self.display_page()

    def move_tag(self, event):
        if not self.edit_mode or self.dragging_tag is None:
            return
        dx = event.x - self.dragging_tag[0]
        dy = event.y - self.dragging_tag[1]
        self.canvas.move(self.dragging_tag[2], dx, dy)
        self.dragging_tag = (event.x, event.y, self.dragging_tag[2])

    def drop_tag(self, event):
        if not self.edit_mode or self.dragging_tag is None:
            return
        self.dragging_tag = None

    def start_pan(self, event):
        self.is_panning = True
        self.pan_start = (event.x, event.y)

    def pan(self, event):
        if self.is_panning:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]
            self.canvas.xview_scroll(-dx, "units")
            self.canvas.yview_scroll(-dy, "units")
            self.pan_start = (event.x, event.y)

    def end_pan(self, event):
        self.is_panning = False

    def zoom_in(self):
        self.zoom_level *= 1.1
        self.display_page()

    def zoom_out(self):
        self.zoom_level /= 1.1
        self.display_page()

    def zoom_with_mouse(self, event):
        if event.state & 0x4:  # Detecta Ctrl presionado
            if event.delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()

    def set_edit_mode(self):
        self.edit_mode = True

    def set_view_mode(self):
        self.edit_mode = False

    def save_notes_to_db(self):
        for (file_name, page_num, x, y), note in self.notes.items():
            self.save_note_to_db(file_name, page_num, x, y,
                                 note["alias"], note["note"])

    def save_note_to_db(self, file_name, page_num, x, y, alias, note):
        self.db_cursor.execute("""
            INSERT INTO notes (file_name, page_num, x, y, alias, note)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (file_name, page_num, x, y, alias, note))
        self.db_connection.commit()

    def update_note_in_db(self, key, new_note):
        file_name, page_num, x, y = key
        self.db_cursor.execute("""
            UPDATE notes
            SET note = ?
            WHERE file_name = ? AND page_num = ? AND x = ? AND y = ?
        """, (new_note, file_name, page_num, x, y))
        self.db_connection.commit()

    def load_notes(self):
        self.notes = self.load_notes_from_db()
        self.display_page()

    def load_notes_from_db(self):
        self.db_cursor.execute(
            "SELECT file_name, page_num, x, y, alias, note FROM notes")
        rows = self.db_cursor.fetchall()
        notes = {}
        for row in rows:
            file_name, page_num, x, y, alias, note = row
            notes[(file_name, page_num, x, y)] = {"alias": alias, "note": note}
        return notes

    def next_page(self):
        if self.pdf_document and self.current_page < len(self.pdf_document) - 1:
            self.current_page += 1
            self.display_page()

    def previous_page(self):
        if self.pdf_document and self.current_page > 0:
            self.current_page -= 1
            self.display_page()

    def load_notes(self):
        self.notes = self.load_notes_from_db()
        self.display_page()

    def __del__(self):
        self.db_connection.close()


# Inicialización de la aplicación
if __name__ == "__main__":
    root = tk.Tk()
    app = InteractivePDFApp(root)
    root.mainloop()
