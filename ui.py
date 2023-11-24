import gradio as gr
import subprocess
import time
import os
import re
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--listen",default="127.0.0.1", help="Listen address")
parser.add_argument("--port", type=int,default=7860, help="Port number")
parser.add_argument("--output_folder",default="./audiobook_output", help="Output folder path")
parser.add_argument("--share", action="store_true", help="Create a public link")
cmd_args = parser.parse_args()

log_path = os.path.join(cmd_args.output_folder, "e2a.log")
class Conversion:
    def __init__(self) -> None:
        self.output_folder = cmd_args.output_folder
        self.current_audiobook_path = None
        self.current_subprocess = None
        pass

    # Create subfolder with input ebook name
    def audiobook_path(self, input_file):
        return os.path.join(self.output_folder, os.path.splitext(os.path.basename(input_file))[0])

    def start_subprocess(self, args, env):
        with open(log_path, "w") as log_file:
            self.current_subprocess = subprocess.Popen(args=args, env=env,
                                        stdout=log_file, stderr=log_file, bufsize=1, text=True)
        
        # Periodically check if the subprocess has exited
        while True and self.current_subprocess is not None:
            exit_code = self.current_subprocess.poll()
            if exit_code is not None:
                print(f"Process exited with code {exit_code}")
                break
            else:
                print("Process is still running...")
                time.sleep(1)  # Wait for a bit before checking again

    def stop_subprocess(self):
        print("Stopping subprocess...", self.current_subprocess)
        if self.current_subprocess:
            self.current_subprocess.terminate()  # or .kill() if terminate does not work
            self.current_subprocess = None
            print("Subprocess stopped")
        else:
            print("No subprocess to stop")

    def convert_epub_to_audiobook(self,
            input_file, 
            tts, log_level, language, newline_mode, chapter_start, chapter_end, 
            output_text, remove_endnotes, 
            azure_tts_key, azure_tts_region,
            voice_name, break_duration, output_format, 
            openai_api_key,
            openai_model, openai_voice, openai_format):
        
        args = ["python", "epub_to_audiobook.py",
                                        "--tts", tts, 
                                        "--log", log_level,
                                        "--language", language,
                                        "--newline_mode", newline_mode,
                                        "--chapter_start", str(chapter_start),
                                        "--chapter_end", str(chapter_end),
                                        "--output_text" if output_text else None,
                                        "--remove_endnotes" if remove_endnotes else None,
                                        "--voice_name", voice_name,
                                        "--break_duration", str(break_duration),
                                        "--output_format", output_format,
                                        "--openai_model", openai_model,
                                        "--openai_voice", openai_voice,
                                        "--openai_format", openai_format,
                                        input_file, self.audiobook_path(input_file)]
        # remove None values from args
        args = [arg for arg in args if arg is not None]
        print("args", args)
        print("Converting EPUB to Audiobook...")
        env = os.environ.copy()
        if tts == "azure":
            env['MS_TTS_KEY'] = azure_tts_key
            env['MS_TTS_REGION'] = azure_tts_region
        elif tts == "openai":
            env['OPENAI_API_KEY'] = openai_api_key
        self.start_subprocess(args, env)
        print("Conversion Finished")

    def preview_book(self, input_file):
        args = ["python", "epub_to_audiobook.py", "--preview", input_file, "."]
        env = os.environ.copy()
        env['MS_TTS_KEY'] = 'x'
        env['MS_TTS_REGION'] = 'x'
        self.start_subprocess(args, env)
        _, total_chapters = Utils().get_progress()
        self.current_audiobook_path = self.audiobook_path(input_file)
        return total_chapters
    
    def list_files(self):
        if self.current_audiobook_path is None:
            return []
        
        if not os.path.isdir(self.current_audiobook_path):
            return []
        files = []

        for file in os.listdir(self.current_audiobook_path):
            files.append(os.path.join(self.current_audiobook_path, file))
        return files

class Utils:
    def __init__(self) -> None:
        pass

    @staticmethod
    def read_log():
        try:
            with open(log_path, "r") as log_file:
                return log_file.read()
        except FileNotFoundError:
            return "Log file not found."

    @staticmethod
    def get_progress():
        result = Utils.read_log()
        # match "Converting chapter %d/%d" using re just first line to get total chapters
        total_chapters = 0
        for line in result.splitlines()[::-1]:
            m = re.search(r"chapter (\d+)/(\d+)", line)
            if m:
                print("m", m)
                current_chapters, total_chapters = int(m.group(1)), int(m.group(2))
                break
        return current_chapters, total_chapters
    
utils = Utils()
conversion = Conversion()

# Create Gradio interface with Blocks
with gr.Blocks() as ui:
    # Common Configuration
    with gr.Row():
        input_file = gr.File(label="Input EPUB File", file_types=[".epub"])
        with gr.Row():
            tts = gr.Dropdown(choices=["azure", "openai"], label="TTS Provider", value="azure")
            language = gr.Textbox(label="Language", value="en-US")
        with gr.Row():
            chapter_start = gr.Number(label="Chapter Start Index", value=1, precision=1)
            chapter_end = gr.Number(label="Chapter End Index", value=-1, precision=1)
        output_folder = gr.Textbox(label="Output Folder Path", value=cmd_args.output_folder, interactive=False)

    with gr.Row():
        newline_mode = gr.Radio(choices=["single", "double"], label="Newline Mode", value="double")
        remove_endnotes = gr.Checkbox(label="Remove Endnotes", value=False)
        output_text = gr.Checkbox(label="Output Text", value=False)
        log = gr.Dropdown(choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], label="Log Level", value="INFO")


    # Azure TTS Tab
    with gr.Tab("Azure TTS"):
        azure_tts_key = gr.Textbox(label="Azure TTS Key", value="")
        azure_tts_region = gr.Textbox(label="Azure TTS Region", value="")
        voice_name = gr.Textbox(label="Azure Voice Name", value="en-US-GuyNeural")
        break_duration = gr.Textbox(label="Break Duration (ms)", value="1250")
        output_format = gr.Dropdown(choices=["audio-16khz-32kbitrate-mono-mp3", "audio-16khz-64kbitrate-mono-mp3", "audio-16khz-128kbitrate-mono-mp3", "audio-24khz-48kbitrate-mono-mp3", "audio-24khz-96kbitrate-mono-mp3", "audio-24khz-160kbitrate-mono-mp3", "audio-48khz-96kbitrate-mono-mp3", "audio-48khz-192kbitrate-mono-mp3"], label="Output Format", value="audio-24khz-48kbitrate-mono-mp3")

    # OpenAI TTS Tab
    with gr.Tab("OpenAI TTS"):
        openai_api_key = gr.Textbox(label="OpenAI API Key", value="")
        openai_model = gr.Dropdown(choices=["tts-1", "tts-1-hd"], label="OpenAI Model", value="tts-1")
        openai_voice = gr.Dropdown(choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"], label="OpenAI Voice", value="alloy")
        openai_format = gr.Dropdown(choices=["mp3", "opus", "aac", "flac"], label="OpenAI Format", value="mp3")

    # Submit & Stop Button
    with gr.Row():
        submit_button = gr.Button("Convert to Audiobook", variant="primary")
        stop_button = gr.Button("Stop", variant="stop")
    log_textarea = gr.TextArea(label="Log", interactive=False, lines=10)
    file_list = gr.File(label="Download Audiobook", file_count="multiple", interactive=False)

    input_file.upload(conversion.preview_book, inputs=[input_file], outputs=[chapter_end])
    
    submit_button.click(
        conversion.convert_epub_to_audiobook, 
        inputs=[
            input_file,
            tts, log, language, newline_mode, chapter_start, chapter_end,
            output_text, remove_endnotes,
            azure_tts_key, azure_tts_region,
            voice_name, break_duration, output_format,
            openai_api_key,
            openai_model, openai_voice, openai_format],
        outputs=[],
    )

    stop_button.click(conversion.stop_subprocess)
    ui.load(utils.read_log, inputs=None, outputs=log_textarea, every=1)
    ui.load(conversion.list_files, inputs=None, outputs=[file_list], every=1)

ui.queue().launch(server_name=cmd_args.listen, server_port=cmd_args.port, share=cmd_args.share)