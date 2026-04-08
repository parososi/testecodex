#!/usr/bin/env ruby
# =============================================================================
# Pied Piper - Utilitario de Compressao em Lote (Ruby)
# =============================================================================
#
# Comprime uma pasta inteira de imagens para o formato .PP usando o
# compressor Pied Piper. Gera um relatorio HTML com as estatisticas.
#
# USO:
#   ruby tools/ppbatch.rb [PASTA] [OPCOES]
#
# OPCOES:
#   -l, --lossless    Modo sem perdas (Middle-Out DPCM + RCT)
#   -q N, --quality N Qualidade 1-100 (padrao: 75, ignorado se -l)
#   -o PASTA          Pasta de saida (padrao: <PASTA>_PP)
#   -r, --report      Gera relatorio HTML com estatisticas
#   -h, --help        Mostra esta ajuda
#
# EXEMPLOS:
#   ruby tools/ppbatch.rb ./fotos -l
#   ruby tools/ppbatch.rb ./imagens -q 90 -r
#   ruby tools/ppbatch.rb ./raw -o ./compressed --lossless --report
#
# =============================================================================

require 'optparse'
require 'fileutils'
require 'json'
require 'time'

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = %w[.jpg .jpeg .png .bmp .tiff .tif .gif .webp
                           .tga .ppm .pgm .pnm .ico .pcx .psd .jp2].freeze

PP_EXT = '.PP'

options = {
  lossless: false,
  quality: 75,
  output_dir: nil,
  report: false,
}

OptionParser.new do |opts|
  opts.banner = "Uso: ruby ppbatch.rb [PASTA] [opcoes]"

  opts.on('-l', '--lossless', 'Modo lossless (sem perdas)') do
    options[:lossless] = true
  end

  opts.on('-q N', '--quality N', Integer, 'Qualidade 1-100 (padrao: 75)') do |n|
    options[:quality] = n.clamp(1, 100)
  end

  opts.on('-o PASTA', '--output PASTA', 'Pasta de saida') do |d|
    options[:output_dir] = d
  end

  opts.on('-r', '--report', 'Gera relatorio HTML') do
    options[:report] = true
  end

  opts.on('-h', '--help', 'Mostra ajuda') do
    puts opts
    exit 0
  end
end.parse!

input_dir = ARGV[0] || '.'

unless Dir.exist?(input_dir)
  warn "ERRO: Pasta nao encontrada: #{input_dir}"
  exit 1
end

output_dir = options[:output_dir] || "#{input_dir}_PP"
FileUtils.mkdir_p(output_dir)

# ---------------------------------------------------------------------------
# Coleta arquivos de imagem
# ---------------------------------------------------------------------------

images = Dir.glob(File.join(input_dir, '**', '*')).select do |f|
  File.file?(f) && SUPPORTED_EXTENSIONS.include?(File.extname(f).downcase)
end

if images.empty?
  puts "Nenhuma imagem encontrada em: #{input_dir}"
  exit 0
end

puts
puts "=" * 60
puts "  PIED PIPER - COMPRESSAO EM LOTE (Ruby utilitario)"
puts "=" * 60
puts "  Pasta:    #{input_dir}"
puts "  Saida:    #{output_dir}"
puts "  Imagens:  #{images.size}"
puts "  Modo:     #{options[:lossless] ? 'LOSSLESS (sem perdas)' : "LOSSY q=#{options[:quality]}"}"
puts "=" * 60
puts

# ---------------------------------------------------------------------------
# Localiza o executavel pp
# ---------------------------------------------------------------------------

script_dir = File.expand_path('..', __dir__)
pp_exec    = File.join(script_dir, 'pp')

unless File.executable?(pp_exec)
  # Tenta como python script
  pp_exec = "python3 #{File.join(script_dir, 'pp')}"
end

# ---------------------------------------------------------------------------
# Comprime cada imagem
# ---------------------------------------------------------------------------

results = []
total_orig = 0
total_comp = 0
errors     = 0
start_all  = Time.now

images.each_with_index do |img_path, idx|
  rel  = img_path.sub(input_dir.chomp('/') + '/', '')
  base = File.basename(img_path, '.*')
  out  = File.join(output_dir, base + PP_EXT)

  orig_size = File.size(img_path)

  # Monta comando pp
  cmd_parts = [pp_exec, 'c', img_path.shellescape, '-o', out.shellescape]
  cmd_parts << '-l' if options[:lossless]
  cmd_parts += ['-q', options[:quality].to_s] unless options[:lossless]
  cmd = cmd_parts.join(' ')

  print "  [#{idx + 1}/#{images.size}] #{rel[0, 45].ljust(45)} "
  $stdout.flush

  t0 = Time.now
  ok = system(cmd, out: '/dev/null', err: '/dev/null')
  elapsed = Time.now - t0

  if ok && File.exist?(out)
    comp_size = File.size(out)
    ratio     = orig_size.to_f / comp_size
    reduction = (1 - comp_size.to_f / orig_size) * 100
    total_orig += orig_size
    total_comp += comp_size
    puts "OK  %6.1f%% em %.2fs" % [reduction, elapsed]
    results << {
      file: rel, orig: orig_size, comp: comp_size,
      ratio: ratio.round(2), reduction: reduction.round(1),
      time: elapsed.round(3), ok: true
    }
  else
    puts "ERRO"
    errors += 1
    results << { file: rel, ok: false }
  end
end

total_time = Time.now - start_all

# ---------------------------------------------------------------------------
# Sumario
# ---------------------------------------------------------------------------

ok_count = results.count { |r| r[:ok] }
avg_reduction = ok_count > 0 ?
  results.select { |r| r[:ok] }.sum { |r| r[:reduction] } / ok_count : 0

puts
puts "=" * 60
puts "  SUMARIO"
puts "=" * 60
puts "  Comprimidos com sucesso: #{ok_count}/#{images.size}"
puts "  Erros:                   #{errors}"
puts "  Tamanho original total:  #{(total_orig / 1024.0 / 1024).round(2)} MB"
puts "  Tamanho comprimido:      #{(total_comp / 1024.0 / 1024).round(2)} MB"
if total_orig > 0
  total_ratio = total_orig.to_f / total_comp
  total_red   = (1 - total_comp.to_f / total_orig) * 100
  puts "  Reducao media:           #{avg_reduction.round(1)}%"
  puts "  Reducao total:           #{total_red.round(1)}%  (#{total_ratio.round(2)}:1)"
end
puts "  Tempo total:             #{total_time.round(1)}s"
puts "=" * 60
puts

# ---------------------------------------------------------------------------
# Relatorio HTML
# ---------------------------------------------------------------------------

if options[:report]
  report_path = File.join(output_dir, 'relatorio.html')

  html = <<~HTML
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
      <meta charset="UTF-8">
      <title>Pied Piper - Relatorio de Compressao</title>
      <style>
        body { font-family: monospace; background: #1a1a2e; color: #e0e0e0; margin: 40px; }
        h1   { color: #00d4aa; }
        h2   { color: #00b4d8; }
        table{ border-collapse: collapse; width: 100%; }
        th   { background: #16213e; color: #00d4aa; padding: 8px; text-align: left; }
        td   { padding: 6px 8px; border-bottom: 1px solid #2a2a4a; }
        tr:hover { background: #16213e; }
        .ok  { color: #00d4aa; }
        .err { color: #ff6b6b; }
        .badge { background: #00d4aa; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; }
      </style>
    </head>
    <body>
    <h1>Pied Piper - Relatorio de Compressao em Lote</h1>
    <p>
      Gerado em: #{Time.now.strftime('%Y-%m-%d %H:%M:%S')}<br>
      Modo: <span class="badge">#{options[:lossless] ? 'LOSSLESS' : "LOSSY q=#{options[:quality]}"}</span><br>
      Pasta: #{input_dir}<br>
      Total: #{ok_count}/#{images.size} comprimidos &nbsp; | &nbsp;
      Reducao media: #{avg_reduction.round(1)}%
    </p>
    <h2>Resultados por arquivo</h2>
    <table>
      <tr><th>Arquivo</th><th>Original</th><th>Comprimido</th><th>Reducao</th><th>Ratio</th><th>Tempo</th><th>Status</th></tr>
  HTML

  results.each do |r|
    if r[:ok]
      html += <<~ROW
        <tr>
          <td>#{r[:file]}</td>
          <td>#{(r[:orig] / 1024.0).round(1)} KB</td>
          <td>#{(r[:comp] / 1024.0).round(1)} KB</td>
          <td>#{r[:reduction]}%</td>
          <td>#{r[:ratio]}:1</td>
          <td>#{r[:time]}s</td>
          <td class="ok">OK</td>
        </tr>
      ROW
    else
      html += "<tr><td>#{r[:file]}</td><td colspan='5'>-</td><td class='err'>ERRO</td></tr>\n"
    end
  end

  html += "</table>\n<p><em>Pied Piper v3.0 - Making the world a better place through better compression.</em></p>\n</body>\n</html>"

  File.write(report_path, html)
  puts "  Relatorio HTML gerado: #{report_path}"
  puts
end
