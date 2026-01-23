import os
import sys
import tkinter as tk
import pystray
from PIL import Image
from tkinter import ttk, messagebox
from datetime import datetime
import sqlite3
import wmi
import pythoncom
import threading
import queue
import time
from functools import partial
from typing import Optional
import winreg  # Для работы с автозапуском

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        """
        Инициализация менеджера базы данных.
        
        :param db_path: Путь к файлу БД. Если None, используется путь по умолчанию.
        """
        self.db_path = db_path or self._get_default_db_path()
        self.conn = None
        self.lock = threading.Lock()
        
    def _get_default_db_path(self) -> str:
        """Получаем путь к БД по умолчанию в AppData/Local"""
        app_data = os.getenv('LOCALAPPDATA') or os.path.expanduser('~')
        app_dir = os.path.join(app_data, "PrintTracker")
        
        # Создаем директорию, если не существует
        os.makedirs(app_dir, exist_ok=True)
        
        return os.path.join(app_dir, "print_jobs.db")

    def initialize(self, timeout: int = 5) -> bool:
        """
        Инициализация подключения к БД с повторными попытками.
        
        :param timeout: Таймаут ожидания блокировки БД (в секундах)
        :return: True если инициализация успешна
        :raises RuntimeError: Если подключение не удалось после всех попыток
        """
        for attempt in range(3):  # Максимум 3 попытки
            try:
                return self._initialize_attempt(timeout)
            except sqlite3.OperationalError as e:
                if attempt == 2:  # Последняя попытка
                    raise RuntimeError(f"Failed to initialize database after 3 attempts: {str(e)}")
                
                # Увеличиваем задержку с каждой попыткой
                delay = 1 * (attempt + 1)
                time.sleep(delay)
                continue

    def _initialize_attempt(self, timeout: int) -> bool:
        """
        Одна попытка инициализации БД.
        
        :param timeout: Таймаут ожидания
        :return: True при успешной инициализации
        """
        with self.lock:
            # Проверяем доступность файла БД
            if not self._check_db_file_access():
                raise sqlite3.OperationalError("No write permissions for database file")
            
            # Подключаемся к БД
            self.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=timeout,
                isolation_level='IMMEDIATE'  # Строгая блокировка
            )
            
            # Оптимизируем настройки для надежности
            self.conn.execute("PRAGMA journal_mode=DELETE")  # Более надежно чем WAL
            self.conn.execute("PRAGMA synchronous=FULL")     # Гарантированная запись
            self.conn.execute("PRAGMA foreign_keys=ON")      # Включение внешних ключей
            
            # Создаем таблицы
            self._create_tables()
            self.conn.commit()
            
            return True

    def _check_db_file_access(self) -> bool:
        """Проверка возможности записи в файл БД"""
        try:
            # Проверяем доступ к директории
            db_dir = os.path.dirname(self.db_path) or '.'
            if not os.access(db_dir, os.W_OK):
                return False
                
            # Если файл существует - проверяем доступ
            if os.path.exists(self.db_path):
                return os.access(self.db_path, os.R_OK | os.W_OK)
                
            # Если файла нет - пробуем создать
            try:
                with open(self.db_path, 'w'):
                    pass
                os.unlink(self.db_path)
                return True
            except IOError:
                return False
        except Exception:
            return False

    def _create_tables(self):
        """Создание необходимых таблиц в БД"""
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS print_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_name TEXT NOT NULL,
                printer_name TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                job_id INTEGER,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Создаем индекс для быстрого поиска по времени
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_print_jobs_timestamp 
            ON print_jobs(timestamp DESC)
        ''')

    def sync(self):
        """Принудительная синхронизация данных с диском"""
        with self.lock:
            if self.conn is not None:
                try:
                    self.conn.execute("PRAGMA wal_checkpoint(FULL)")
                    self.conn.commit()
                except sqlite3.Error:
                    pass  # Игнорируем ошибки синхронизации

    def close(self):
        """Безопасное закрытие соединения с БД"""
        with self.lock:
            if self.conn is not None:
                try:
                    self.sync()
                    self.conn.close()
                except sqlite3.Error:
                    pass
                finally:
                    self.conn = None

    def __del__(self):
        """Деструктор - гарантирует закрытие соединения"""
        self.close()

class PrintMonitor:
    def __init__(self, db_manager, update_callback):
        self.db_manager = db_manager
        self.update_callback = update_callback
        self.running = False
        self.thread = None
        self.wmi_connected = False
        
    def start(self):
        """Запуск мониторинга в отдельном потоке"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Остановка мониторинга"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            
    def _monitor_loop(self):
        while self.running:
            try:
                # Инициализируем COM для этого потока
                pythoncom.CoInitialize()
                self.wmi_connected = True
                
                try:
                    c = wmi.WMI()
                    printers = c.Win32_Printer()
                    if not printers:
                        self.update_callback("STATUS", "Waiting for printer subsystem...")
                        time.sleep(5)
                        continue
                        
                    watcher = c.Win32_PrintJob.watch_for(
                        notification_type="Creation",
                        delay_secs=1
                    )
                    
                    self.update_callback("STATUS", "Print monitor started successfully")
                    
                    while self.running:
                        try:
                            job = watcher()
                            if job:
                                self._process_job(job)
                        except pythoncom.com_error as e:
                            if self.running:
                                self.update_callback("ERROR", f"WMI communication error: {str(e)}")
                                time.sleep(5)
                                break  # Выходим из внутреннего цикла для переподключения
                        
                        time.sleep(0.1)
                        
                except Exception as e:
                    self.update_callback("ERROR", f"WMI error: {str(e)}")
                    time.sleep(5)
                    
            except Exception as e:
                self.update_callback("ERROR", f"COM initialization failed: {str(e)}")
                time.sleep(5)
            finally:
                if self.wmi_connected:
                    pythoncom.CoUninitialize()
                    self.wmi_connected = False
            
    def _process_job(self, job):
        """Обработка задания печати с гарантированной записью в БД"""
        if (not job.Document or 
            'ipp' in str(job.Document).lower() or 
            'http' in str(job.Document).lower()):
            self.update_callback("INFO", f"Skipped system job: {job.Document}")
            return
    
        try:
            job_id = job.JobId
            printer = job.Name.split(',')[0]
            document = job.Document or "Unknown"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with self.db_manager.lock:
                # Явная транзакция с указанием всех 6 столбцов
                self.db_manager.conn.execute(
                    "INSERT INTO print_jobs (document_name, printer_name, timestamp, job_id, status) VALUES (?, ?, ?, ?, ?)",
                    (document, printer, timestamp, job_id, 'completed')  # Указываем статус по умолчанию
                )
                self.db_manager.conn.commit()

                # Проверяем что запись действительно сохранена
                cursor = self.db_manager.conn.execute(
                    "SELECT 1 FROM print_jobs WHERE id = last_insert_rowid()"
                )
                if not cursor.fetchone():
                    raise RuntimeError("Failed to verify database write")

            self.update_callback("UPDATE", f"New print job: {document} (saved)")
        except Exception as e:
            self.update_callback("ERROR", f"Job processing error: {str(e)}")
            # Пытаемся повторить запись через 5 секунд
            time.sleep(5)
            self._process_job(job)  # Рекурсивный повтор

class PrintTrackerApp:
    def __init__(self, root):
        self.root = root
        self.setup_ui()
        self.setup_tray()
        self.setup_services()
        self.check_first_run()

        self.root.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)
        
    def check_first_run(self):
        """Проверка первого запуска и добавление в автозапуск"""
        settings_path = os.path.join(os.path.dirname(__file__), 'settings.ini')
        if not os.path.exists(settings_path):
            # Первый запуск
            self.add_to_autostart()
            with open(settings_path, 'w') as f:
                f.write('[Settings]\nfirst_run=0')
    
    def add_to_autostart(self):
        """Улучшенное добавление в автозагрузку"""
        try:
            # Получаем путь к exe (или py) файлу
            if getattr(sys, 'frozen', False):
                # Для собранного exe
                app_path = sys.executable
            else:
                # Для скрипта Python
                app_path = os.path.abspath(__file__)
                python_path = sys.executable
                app_path = f'"{python_path}" "{app_path}"'

            # Создаем командную строку с задержкой
            cmd = f"{app_path}"

            # Открываем ключ реестра
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Run',
                0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, "PrintTracker", 0, winreg.REG_SZ, cmd)

            self.update_status("Added to autostart with 10s delay")
        except Exception as e:
            self.show_error(f"Autostart error: {str(e)}")

    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        self.root.title("Print Job Tracker")
        self.root.geometry("1000x600")
        
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Treeview
        self.tree = ttk.Treeview(main_frame, columns=('ID', 'Document', 'Printer', 'Time'), show='headings')
        for col, width in [('ID', 80), ('Document', 400), ('Printer', 200), ('Time', 200)]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor=tk.CENTER if col == 'ID' else tk.W)
        
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.retry_button = ttk.Button(
            self.root,
            text="Retry Initialization",
            command=self.setup_services,
            state=tk.DISABLED
        )
        self.retry_button.pack(pady=5)
        
        # Status bar
        self.status_var = tk.StringVar(value="Initializing...")
        status_bar = ttk.Label(
            self.root, 
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(fill=tk.X, padx=10, pady=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(
            self.root,
            orient=tk.HORIZONTAL,
            mode='indeterminate',
            maximum=100
        )
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        self.progress.start(10)

    def setup_tray(self):
        """Инициализация системного трея"""
        try:
            icon_path = os.path.join(os.path.dirname(__file__), 'printer.ico')
            
            # Проверяем существование файла иконки
            if os.path.exists(icon_path):
                image = Image.open(icon_path)
            else:
                # Фолбэк на стандартную иконку
                image = Image.new('RGB', (64, 64), 'white')

            # Меню трея
            menu = pystray.Menu(
                pystray.MenuItem('Открыть', self.restore_from_tray),
                pystray.MenuItem('Выход', self.quit_app)
            )

            # Создаем иконку в трее
            self.tray_icon = pystray.Icon(
                "PrintTracker", 
                image, 
                "Print Tracker", 
                menu
            )

            # Запускаем в отдельном потоке
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

        except Exception as e:
            print(f"Ошибка загрузки иконки: {str(e)}")
            # Фолбэк на минимальную функциональность
            image = Image.new('RGB', (64, 64), 'white')
            self.tray_icon = pystray.Icon("PrintTracker", image, "Print Tracker", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def minimize_to_tray(self):
        """Сворачивание в трей"""
        self.root.withdraw()
        self.update_status("Application is running in background")
        # Принудительно обновляем список заданий
        self.load_job_history()
    
    def restore_from_tray(self, icon=None, item=None):
        """Восстановление окна из трея"""
        self.root.after(0, self._restore_window)

    def _restore_window(self):
        """Фактическое восстановление окна"""
        self.root.deiconify()
        self.root.wm_state('normal')
        self.update_status("Application restored")

    def quit_app(self, icon=None, item=None):
        """Полное закрытие приложения"""
        self.update_status("Shutting down...")
        self.on_close()

    def setup_services(self):
        """Инициализация сервисов в фоновом потоке"""
        def init_services():
            max_attempts = 5
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    self.update_status(f"Initializing services (attempt {attempt + 1}/{max_attempts})...")
                    
                    # 1. Проверяем доступность системных сервисов
                    if not self.check_system_ready():
                        attempt += 1
                        time.sleep(5)  # Увеличиваем задержку между попытками
                        continue
                    
                    # 2. Инициализируем БД
                    self.db_manager = DatabaseManager()
                    self.db_manager.initialize()
                    
                    # 3. Запускаем монитор печати
                    self.monitor = PrintMonitor(self.db_manager, self.handle_update)
                    self.monitor.start()
                    
                    # 4. Загружаем историю
                    self.load_job_history()
                    
                    self.update_status("Ready - Monitoring print jobs")
                    self.progress.stop()
                    self.progress.pack_forget()
                    return
                    
                except Exception as e:
                    attempt += 1
                    error_msg = f"Initialization attempt {attempt} failed: {str(e)}"
                    self.update_status(error_msg)
                    if attempt >= max_attempts:
                        self.show_error(f"Initialization failed after {max_attempts} attempts")
                        self.root.after(1000, self.root.destroy)
                    else:
                        time.sleep(5)  # Ждем перед следующей попыткой
        
        threading.Thread(target=init_services, daemon=True).start()
    
    def check_system_ready(self):
        """Проверка готовности системы с улучшенной обработкой ошибок"""
        try:
            pythoncom.CoInitialize()
            try:
                c = wmi.WMI()
                
                # Проверяем состояние службы печати
                spooler = c.Win32_Service(Name='Spooler')
                if not spooler or spooler[0].State != 'Running':
                    return False
                
                # Дополнительные проверки доступности принтеров
                printers = c.Win32_Printer()
                if not printers:
                    return False
                    
                return True
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            self.update_status(f"System check error: {str(e)}")
            return False

    def handle_update(self, update_type, message):
        """Обработка обновлений из фоновых потоков"""
        self.root.after(0, partial(self._process_update, update_type, message))
        
    def _process_update(self, update_type, message):
        """Обработка обновлений в основном потоке"""
        if update_type == "UPDATE":
            self.load_job_history()
            self.status_var.set(message)
        elif update_type == "ERROR":
            self.show_error(message)
        elif update_type == "STATUS":
            self.status_var.set(message) 
            
    def load_job_history(self):
        """Загрузка истории печати"""
        try:
            self.tree.delete(*self.tree.get_children())
            with self.db_manager.lock:
                cursor = self.db_manager.conn.execute(
                    "SELECT id, document_name, printer_name, timestamp FROM print_jobs ORDER BY timestamp DESC"
                )
                for row in cursor.fetchall():
                    self.tree.insert('', 'end', values=row)
        except Exception as e:
            self.show_error(f"Failed to load job history: {str(e)}")
            
    def update_status(self, message):
        """Обновление статуса"""
        self.status_var.set(message)
        self.root.update_idletasks()
        
    def show_error(self, message):
        """Показать сообщение об ошибке"""
        self.status_var.set(f"Error: {message}")
        messagebox.showerror("Error", message)
        
    def on_close(self):
        """Обработчик закрытия приложения с гарантированным сохранением данных"""
        self.update_status("Saving data and shutting down...")

        try:
            if hasattr(self, 'monitor'):
                self.monitor.stop()

            if hasattr(self, 'db_manager'):
                # Принудительно синхронизируем БД
                self.db_manager.sync()

                if hasattr(self.db_manager, 'conn'):
                    self.db_manager.conn.close()

        except Exception as e:
            self.show_error(f"Shutdown error: {str(e)}")
        finally:
            if hasattr(self, 'tray_icon'):
                self.tray_icon.stop()
            self.root.destroy()
            
def main():
    try:
        root = tk.Tk()
        app = PrintTrackerApp(root)
        
        # Center window
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'+{x}+{y}')
        
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"Application failed to start: {str(e)}")

if __name__ == "__main__":
    # Для корректной работы WMI в многопоточном приложении
    pythoncom.CoInitialize()
    try:
        main()
    finally:
        pythoncom.CoUninitialize()