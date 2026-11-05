import tkinter as tk
from tkinter import *
from tkinter.ttk import Scale
import webcam_module



class ElderlyMonitorWindow(tk.Tk):
    """
    Simplified UI for Elderly Inactivity Monitoring.
    """
    
    def __init__(self):
        super().__init__()
        self.geometry('{}x{}'.format(800, 700))
        self.resizable(True, True)
        self.minsize(800, 700)
        self.title('Elderly Inactivity Monitor')
        self.background_color = '#2C3E50'
        
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=10)
        self.grid_rowconfigure(2, weight=2)
        self.grid_columnconfigure(0, weight=1)
        
        # ===== TOP FRAME - Title and Status =====
        self.top_frame = Frame(self, background=self.background_color, height=80)
        
        self.title_label = Label(
            self.top_frame, 
            text="👴 Elderly Inactivity Monitor",
            font=('Arial', 20, 'bold'),
            fg='white', 
            background=self.background_color
        )
        self.title_label.pack(pady=20)
        
        self.top_frame.grid(row=0, column=0, sticky='nsew')
        
        # ===== MIDDLE FRAME - Video Display =====
        self.mid_frame = Frame(
            self, 
            background='#34495E', 
            bd=4, 
            highlightbackground='#1ABC9C', 
            highlightthickness=2
        )
        
        self.content_frame = Frame(self.mid_frame, background='#34495E')
        self.webcam_frame = Label(self.content_frame, background='black')
        self.webcam_frame.place(x=0, y=0, relheight=1, relwidth=1)
        
        # Placeholder text
        self.placeholder_label = Label(
            self.content_frame,
            text="Click 'Start Monitoring' to begin",
            font=('Arial', 16),
            fg='white',
            background='#34495E'
        )
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor=CENTER)
        
        self.content_frame.place(relheight=1, relwidth=1)
        self.mid_frame.grid(row=1, column=0, sticky='nsew', padx=10, pady=10)
        
        # ===== BOTTOM FRAME - Controls =====
        self.bottom_frame = Frame(self, background=self.background_color)
        
        # Control buttons
        button_frame = Frame(self.bottom_frame, background=self.background_color)
        
        self.start_btn = Button(
            button_frame,
            text='▶ Start Monitoring',
            font=('Arial', 12, 'bold'),
            bg='#27AE60',
            fg='white',
            activebackground='#2ECC71',
            activeforeground='white',
            width=18,
            height=2,
            command=self.start_monitoring
        )
        self.start_btn.grid(row=0, column=0, padx=10, pady=10)
        
        self.stop_btn = Button(
            button_frame,
            text='⏹ Stop Monitoring',
            font=('Arial', 12, 'bold'),
            bg='#E74C3C',
            fg='white',
            activebackground='#C0392B',
            activeforeground='white',
            width=18,
            height=2,
            state=DISABLED,
            command=self.stop_monitoring
        )
        self.stop_btn.grid(row=0, column=1, padx=10, pady=10)
        
        self.reset_btn = Button(
            button_frame,
            text='🔄 Reset Timer',
            font=('Arial', 12, 'bold'),
            bg='#F39C12',
            fg='white',
            activebackground='#E67E22',
            activeforeground='white',
            width=18,
            height=2,
            command=self.reset_timer
        )
        self.reset_btn.grid(row=0, column=2, padx=10, pady=10)
        
        button_frame.pack(pady=10)
        
        # Settings frame
        settings_frame = Frame(self.bottom_frame, background=self.background_color)
        
        Label(
            settings_frame,
            text="Alert Threshold (seconds):",
            font=('Arial', 10),
            fg='white',
            background=self.background_color
        ).grid(row=0, column=0, padx=10, sticky=W)
        
        self.threshold_var = IntVar(value=30)
        self.threshold_scale = Scale(
            settings_frame,
            from_=5,
            to=300,  # 5 seconds to 5 minutes (300 seconds)
            orient=HORIZONTAL,
            variable=self.threshold_var,
            length=300,
            command=self.update_threshold
        )
        self.threshold_scale.grid(row=0, column=1, padx=10)
        
        self.threshold_label = Label(
            settings_frame,
            text="30 sec",
            font=('Arial', 10, 'bold'),
            fg='#1ABC9C',
            background=self.background_color,
            width=10
        )
        self.threshold_label.grid(row=0, column=2, padx=10)
        
        settings_frame.pack(pady=10)
        
        # Close button
        self.close_btn = Button(
            self.bottom_frame,
            text='✖ Close Application',
            font=('Arial', 10),
            bg='#95A5A6',
            fg='white',
            activebackground='#7F8C8D',
            activeforeground='white',
            width=20,
            command=self.close_application
        )
        self.close_btn.pack(pady=10)
        
        self.bottom_frame.grid(row=2, column=0, sticky='nsew')
        
        # Monitoring state
        self.is_monitoring = False
    
    def start_monitoring(self):
        """Start webcam monitoring."""
        if not self.is_monitoring:
            self.placeholder_label.place_forget()
            webcam_module.show_webcam(self)
            self.is_monitoring = True
            self.start_btn.config(state=DISABLED)
            self.stop_btn.config(state=NORMAL)
    
    def stop_monitoring(self):
        """Stop webcam monitoring."""
        if self.is_monitoring:
            webcam_module.stop_webcam()
            self.is_monitoring = False
            self.start_btn.config(state=NORMAL)
            self.stop_btn.config(state=DISABLED)
            self.placeholder_label.place(relx=0.5, rely=0.5, anchor=CENTER)
    
    def reset_timer(self):
        """Reset the inactivity timer."""
        if webcam_module.webcam_monitor:
            webcam_module.webcam_monitor.reset_monitor()
    
    def update_threshold(self, value):
        """Update the alert threshold."""
        seconds = int(float(value))
        self.threshold_label.config(text=f"{seconds} sec")
        if webcam_module.webcam_monitor:
            webcam_module.webcam_monitor.set_safety_threshold(seconds)
    
    def close_application(self):
        """Close the application."""
        if self.is_monitoring:
            self.stop_monitoring()
        self.destroy()


def on_closing():
    """Handle window close event."""
    from tkinter import messagebox
    if messagebox.askokcancel("Quit", "Do you want to quit?"):
        if webcam_module.webcam_monitor:
            webcam_module.stop_webcam()
        mainWin.destroy()


if __name__ == "__main__":
    mainWin = ElderlyMonitorWindow()
    mainWin.protocol("WM_DELETE_WINDOW", on_closing)
    mainWin.mainloop()
