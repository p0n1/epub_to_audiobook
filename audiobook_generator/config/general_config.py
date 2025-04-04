class GeneralConfig:
    def __init__(self, args):
        # General arguments
        self.input_file = getattr(args, 'input_file', None)
        self.output_folder = getattr(args, 'output_folder', None)
        self.preview = getattr(args, 'preview', None)
        self.output_text = getattr(args, 'output_text', None)
        self.log = getattr(args, 'log', None)
        self.log_file = None
        self.no_prompt = getattr(args, 'no_prompt', None)
        self.worker_count = getattr(args, 'worker_count', None)

        # Book parser specific arguments
        self.title_mode = getattr(args, 'title_mode', None)
        self.newline_mode = getattr(args, 'newline_mode', None)
        self.chapter_start = getattr(args, 'chapter_start', None)
        self.chapter_end = getattr(args, 'chapter_end', None)
        self.remove_endnotes = getattr(args, 'remove_endnotes', None)
        self.remove_reference_numbers = getattr(args, 'remove_reference_numbers', None)
        self.search_and_replace_file = getattr(args, 'search_and_replace_file', None)

        # TTS provider: common arguments
        self.tts = getattr(args, 'tts', None)
        self.language = getattr(args, 'language', None)
        self.voice_name = getattr(args, 'voice_name', None)
        self.output_format = getattr(args, 'output_format', None)
        self.model_name = getattr(args, 'model_name', None)

        # OpenAI specific arguments
        self.instructions = getattr(args, 'instructions', None)
        self.speed = getattr(args, 'speed', None)

        # TTS provider: Azure & Edge TTS specific arguments
        self.break_duration = getattr(args, 'break_duration', None)

        # TTS provider: Edge specific arguments
        self.voice_rate = getattr(args, 'voice_rate', None)
        self.voice_volume = getattr(args, 'voice_volume', None)
        self.voice_pitch = getattr(args, 'voice_pitch', None)
        self.proxy = getattr(args, 'proxy', None)

        # TTS provider: Piper specific arguments
        self.piper_path = getattr(args, 'piper_path', None)
        self.piper_docker_image = getattr(args, 'piper_docker_image', None)
        self.piper_speaker = getattr(args, 'piper_speaker', None)
        self.piper_noise_scale = getattr(args, 'piper_noise_scale', None)
        self.piper_noise_w_scale = getattr(args, 'piper_noise_w_scale', None)
        self.piper_length_scale = getattr(args, 'piper_length_scale', None)
        self.piper_sentence_silence = getattr(args, 'piper_sentence_silence', None)

    def __str__(self):
        return ",\n".join(f"{key}={value}" for key, value in self.__dict__.items())
