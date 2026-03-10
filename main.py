import os
import sys
import traceback
from datetime import datetime

# Logging setup to catch startup errors
LOG_FILE = "crash_log.txt"
def log_error(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] {msg}\n")
    except:
        pass

try:
    log_error("--- Application Starting ---")
except:
    pass

try:
    import customtkinter as ctk
    from tkinterdnd2 import DND_FILES, TkinterDnD
    from tkinter import filedialog, messagebox
    from PIL import Image
    import re
    import threading
except Exception as e:
    log_error(f"IMPORT ERROR: {traceback.format_exc()}")
    sys.exit(1)

# Import Generator and Extractors
try:
    from generator_sierra_v7_alt import SierraPDFGeneratorV7 as SierraPDFGenerator
    from extractors import ExtractorFactory
    from utils import resource_path
    from version import VERSION
except Exception as e:
    log_error(f"LOCAL IMPORT ERROR: {traceback.format_exc()}")
    sys.exit(1)

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        # --- Window Config ---
        self.title("Sierra Automação - Processamento de Orçamentos")
        self.geometry("720x680")
        
        # Colors (Sierra Light Theme)
        self.col_bg = "#f5f7fa"        # Very light grey/blue ish
        self.col_panel = "#ffffff"     # White for cards/panels
        self.col_header = "#ffffff"
        self.col_primary = "#0047AB"   # Cobalt/Royal Blue
        self.col_primary_hover = "#003380"
        self.col_text = "#333333"
        self.col_text_light = "#666666"

        self.configure(bg=self.col_bg)

        # --- Data ---
        self.file_list = []      # List of file paths
        self.file_widgets = {}   # Map path -> widget_frame (for removal)
        self.status_labels = {}  # Map path -> status_label (for individual updates)

        # --- Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Main Content
        self.grid_rowconfigure(2, weight=0) # Footer

        self.setup_header()
        self.setup_content()
        self.setup_footer()

        # --- DnD ---
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.drop_files)

    def setup_header(self):
        self.header_frame = ctk.CTkFrame(self, fg_color=self.col_header, corner_radius=0, height=80)
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.header_frame.grid_propagate(False)

        # Logo
        logo_path = resource_path("logo.png")
        if os.path.exists(logo_path):
            try:
                pil_image = Image.open(logo_path)
                ratio = pil_image.width / pil_image.height
                h = 50
                w = int(h * ratio)
                self.logo_img = ctk.CTkImage(light_image=pil_image, size=(w, h))
                self.lbl_logo = ctk.CTkLabel(self.header_frame, text="", image=self.logo_img)
                self.lbl_logo.pack(side="left", padx=25, pady=15)
            except:
                self.create_fallback_logo()
        else:
            self.create_fallback_logo()

        self.lbl_title = ctk.CTkLabel(
            self.header_frame, 
            text="Automação de Orçamentos", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="normal"),
            text_color=self.col_text
        )
        self.lbl_title.pack(side="left", padx=(10, 0))

        # Version Label (Header)
        self.lbl_version = ctk.CTkLabel(self.header_frame, text=f"Versão {VERSION}", font=("Segoe UI", 10), text_color="#eeeeee")
        self.lbl_version.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=5)

    def create_fallback_logo(self):
        self.lbl_logo = ctk.CTkLabel(self.header_frame, text="SIERRA", text_color=self.col_primary, font=("Arial Black", 24))
        self.lbl_logo.pack(side="left", padx=25, pady=15)

    def setup_content(self):
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(10, 8))
        
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=0) # Drop
        self.content_frame.grid_rowconfigure(1, weight=0) # Label
        self.content_frame.grid_rowconfigure(2, weight=1) # List

        # Styled Drop Area
        self.drop_frame = ctk.CTkFrame(self.content_frame, fg_color=self.col_panel, corner_radius=15, border_width=2, border_color="#dce1e8")
        self.drop_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.lbl_drop_icon = ctk.CTkLabel(self.drop_frame, text="☁️", font=("Segoe UI Emoji", 36))
        self.lbl_drop_icon.pack(pady=(15, 3))
        
        self.lbl_drop_text = ctk.CTkLabel(
            self.drop_frame, 
            text="Arraste e solte seus arquivos PDF aqui", 
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self.col_text
        )
        self.lbl_drop_text.pack(pady=(0, 5))
        
        self.btn_select_manual = ctk.CTkButton(
            self.drop_frame,
            text="Selecionar do Computador",
            command=self.select_files_manual,
            fg_color="#e0e0e0",
            text_color="#333333",
            hover_color="#d0d0d0",
            corner_radius=8,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal")
        )
        self.btn_select_manual.pack(pady=(8, 15))

        # File List Heading
        self.lbl_files = ctk.CTkLabel(self.content_frame, text="ARQUIVOS SELECIONADOS", font=("Segoe UI", 11, "bold"), text_color=self.col_text_light)
        self.lbl_files.grid(row=1, column=0, sticky="w", pady=(0, 3))

        # Scrollable List
        self.scroll_files = ctk.CTkScrollableFrame(
            self.content_frame, 
            label_text="", 
            fg_color="#ffffff", # White background for the list area itself
            border_width=1,
            border_color="#e0e0e0",
            scrollbar_button_color="#d0d0d0",
            scrollbar_button_hover_color="#a0a0a0"
        )
        self.scroll_files.grid(row=2, column=0, sticky="nsew")

    def setup_footer(self):
        self.footer_frame = ctk.CTkFrame(self, fg_color=self.col_panel, height=60, corner_radius=0)
        self.footer_frame.grid(row=2, column=0, sticky="ew")
        self.footer_frame.grid_propagate(False)
        
        # Separator
        line = ctk.CTkFrame(self.footer_frame, height=1, fg_color="#e0e0e0")
        line.pack(fill="x", side="top")
        
        self.footer_inner = ctk.CTkFrame(self.footer_frame, fg_color="transparent")
        self.footer_inner.pack(fill="both", expand=True, padx=20)
        
        # Use grid for fixed positioning (prevents button resize)
        self.footer_inner.grid_columnconfigure(0, weight=1)  # Status expands
        self.footer_inner.grid_columnconfigure(1, weight=0)  # Limpar fixed
        self.footer_inner.grid_columnconfigure(2, weight=0)  # Processar fixed
        
        # Left: Global Status
        self.lbl_global_status = ctk.CTkLabel(self.footer_inner, text="Aguardando arquivos...", text_color="gray", font=("Segoe UI", 11), anchor="w")
        self.lbl_global_status.grid(row=0, column=0, sticky="w", pady=10)
        
        # Right: Limpar
        self.btn_clear = ctk.CTkButton(
            self.footer_inner, 
            text="Limpar", 
            command=self.clear_list,
            fg_color="#ffebee", 
            text_color="#c62828",
            hover_color="#ffcdd2",
            corner_radius=8,
            width=80,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.btn_clear.grid(row=0, column=1, padx=(0, 10), pady=10)

        # Right: Processar
        self.btn_run = ctk.CTkButton(
            self.footer_inner,
            text="PROCESSAR ➤",
            command=self.start_processing,
            fg_color=self.col_primary,
            hover_color=self.col_primary_hover,
            corner_radius=8,
            height=38,
            width=160,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            state="disabled"
        )
        self.btn_run.grid(row=0, column=2, pady=10)

    # --- Logic ---

    def drop_files(self, event):
        try:
            raw_data = event.data
            paths = self.parse_dnd_paths(raw_data)
            for p in paths:
                 p = p.strip()
                 if p and p.lower().endswith(".pdf") and p not in self.file_list:
                      self.add_file(p)
        except Exception as e:
            messagebox.showerror("Erro ao soltar", str(e))

    def parse_dnd_paths(self, data):
        if not data: return []
        pattern = r'\{([^{}]+)\}|([^{}\s]+)'
        matches = re.findall(pattern, data)
        results = []
        for m in matches:
             path = m[0] if m[0] else m[1]
             results.append(path)
        return results

    def select_files_manual(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF Files", "*.pdf")])
        for p in files:
             if p not in self.file_list:
                  self.add_file(p)

    def add_file(self, path):
        self.file_list.append(path)
        
        # Container for the row + separator
        row_container = ctk.CTkFrame(self.scroll_files, fg_color="transparent")
        row_container.pack(fill="x", pady=(1, 0))

        # Create Compact Row (Frame)
        card = ctk.CTkFrame(row_container, fg_color="transparent", corner_radius=0, height=28)
        card.pack(fill="x", padx=5)
        
        # Filename
        filename = os.path.basename(path)
        
        # Icon (Small)
        lbl_icon = ctk.CTkLabel(card, text="📄", font=("Segoe UI Emoji", 12))
        lbl_icon.pack(side="left", padx=(5, 8))
        
        # Name
        lbl_name = ctk.CTkLabel(card, text=filename, font=("Segoe UI", 11), text_color=self.col_text)
        lbl_name.pack(side="left", fill="x", expand=False)
        
        # Status Label (Individual) - Compact
        lbl_status = ctk.CTkLabel(card, text="Pendente", font=("Segoe UI", 10), text_color="#f57f17", width=70, anchor="e")
        lbl_status.pack(side="left", padx=10, fill="x", expand=True)
        self.status_labels[path] = lbl_status
        
        # Remove Button (Icon only, small)
        btn_del = ctk.CTkButton(
            card, text="✕", width=20, height=20, 
            fg_color="transparent", hover_color="#ffebee", text_color="#c62828", font=("Segoe UI", 12, "bold"),
            command=lambda p=path: self.remove_file(p)
        )
        btn_del.pack(side="right", padx=2)

        # Subtle Separator Line
        separator = ctk.CTkFrame(row_container, height=1, fg_color="#f0f0f0")
        separator.pack(fill="x", padx=10)
        
        # Store for cleanup
        self.file_widgets[path] = row_container
        
        self.update_global_status()

    def remove_file(self, path):
        if path in self.file_list:
            self.file_list.remove(path)
        if path in self.file_widgets:
            self.file_widgets[path].destroy()
            del self.file_widgets[path]
        if path in self.status_labels:
            del self.status_labels[path]
        
        self.update_global_status()

    def clear_list(self):
        for w in self.file_widgets.values():
            w.destroy()
        self.file_list = []
        self.file_widgets = {}
        self.status_labels = {}
        self.update_global_status()

    def update_global_status(self):
        count = len(self.file_list)
        if count == 0:
            self.lbl_global_status.configure(text="Aguardando arquivos...")
            self.btn_run.configure(state="disabled")
        else:
            self.lbl_global_status.configure(text=f"{count} arquivos na fila.")
            self.btn_run.configure(state="normal")

    def start_processing(self):
        if not self.file_list: return
        self.btn_run.configure(state="disabled")
        self.btn_clear.configure(state="disabled")
        self.btn_select_manual.configure(state="disabled")
        threading.Thread(target=self.process_batch).start()

    def process_batch(self):
        total = len(self.file_list)
        success_count = 0
        errors = []
        
        orcamentos_dir = self.get_output_dir()
        os.makedirs(orcamentos_dir, exist_ok=True)

        for i, file_path in enumerate(self.file_list):
            filename = os.path.basename(file_path)
            
            # Update UI
            self.lbl_global_status.configure(text=f"Processando ({i+1}/{total}): {filename}...")
            if file_path in self.status_labels:
                self.status_labels[file_path].configure(text="Processando...", text_color=self.col_primary)
            
            try:
                # 1. Extract
                extractor = ExtractorFactory.get_extractor(file_path)
                if not extractor:
                    raise Exception("Seguradora não identificada.")
                
                data = extractor.extract()
                
                # 2. Generate
                segurado_raw = str(data.get('segurado') or 'Cliente')
                
                # Clean PJ suffixes for filename
                name_clean = segurado_raw.upper()
                pj_suffixes = [r'\bLTDA\b', r'\bS/A\b', r'\bS\.A\.\b', r'\bME\b', r'\bEPP\b', r'\bSA\b']
                for suffix in pj_suffixes:
                    name_clean = re.sub(suffix, '', name_clean)
                name_clean = name_clean.strip()

                parts_name = name_clean.split()
                if len(parts_name) >= 2: 
                    name_str = f"{parts_name[0]}.{parts_name[-1]}"
                elif parts_name:
                    name_str = parts_name[0]
                else:
                    name_str = "Cliente"
                
                insurer_code = str(data.get('insurer', 'UNK'))[:3].upper()
                now_str = datetime.now().strftime("%d.%m.%y_%H.%M.%S")
                
                out_name = f"Orçamento.{name_str}.{insurer_code}.{now_str}.pdf"
                out_name = re.sub(r'[<>:"/\\|?*]', '', out_name)
                
                output_path = os.path.join(orcamentos_dir, out_name)
                
                generator = SierraPDFGenerator(data, output_path)
                generator.generate()
                
                success_count += 1
                if file_path in self.status_labels:
                    self.status_labels[file_path].configure(text="Concluído", text_color="#2e7d32")

            except Exception as e:
                print(f"Error {filename}: {e}")
                errors.append(f"{filename}: {str(e)}")
                if file_path in self.status_labels:
                    self.status_labels[file_path].configure(text="Erro", text_color="#c62828")

        # Finished
        self.lbl_global_status.configure(text=f"Concluído! {success_count}/{total} ok.")
        self.btn_run.configure(state="normal")
        self.btn_clear.configure(state="normal")
        self.btn_select_manual.configure(state="normal")
        
        msg = f"Processamento finalizado.\nSucessos: {success_count}\nErros: {len(errors)}"
        if errors: msg += "\n\nFalhas:\n" + "\n".join(errors)
        
        messagebox.showinfo("Resultados", msg)
        os.startfile(orcamentos_dir)

    def get_output_dir(self):
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, "orcamentos")

if __name__ == "__main__":
    try:
        if hasattr(sys, 'frozen'):
            # Fix for PyInstaller and multiprocessing/recursion if needed (not strictly needed for just threading)
            pass
        
        app = App()
        app.mainloop()
    except Exception as e:
        err_msg = traceback.format_exc()
        print(err_msg)
        log_error(f"CRITICAL ERROR:\n{err_msg}")
        # Try to show a messagebox if possible
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Erro na Inicialização", f"Ocorreu um erro ao iniciar a aplicação:\n\n{e}\n\nVerifique o arquivo 'crash_log.txt' para mais detalhes.")
            root.destroy()
        except:
            pass
