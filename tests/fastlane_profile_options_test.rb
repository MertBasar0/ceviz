# Exercise the installed Fastlane/Sigh option validator, not an action mock.
# No lane, signing action, credential request, or network call is executed.
ENV["FASTLANE_SKIP_UPDATE_CHECK"] = "1"
ENV["FASTLANE_OPT_OUT_USAGE"] = "1"
require "fastlane"
require "sigh/options"

UI = FastlaneCore::UI unless defined?(UI)

# Registering the Fastfile definitions must not execute any lane block.
def default_platform(_name); end
def desc(_text); end
def lane(_name); end
def platform(_name)
  yield
end

load File.expand_path("../fastlane/Fastfile", __dir__)

def check_profile_option(condition, message)
  raise message unless condition
end

# Isolate the actual option defaults from an operator's optional SIGH overrides.
mode_environment = %w[SIGH_AD_HOC SIGH_DEVELOPMENT SIGH_DEVELOPER_ID]
saved_environment = mode_environment.to_h { |name| [name, ENV[name]] }
mode_environment.each { |name| ENV.delete(name) }

begin
  modes = {
    "app-store" => [{}, false, false],
    "development" => [{ development: true }, true, false],
    "ad-hoc" => [{ adhoc: true }, false, true]
  }
  modes.each do |mode, (expected_options, development, adhoc)|
    options = provisioning_mode_options(mode)
    check_profile_option(options == expected_options, "Wrong profile options for #{mode}")
    configuration = FastlaneCore::Configuration.create(Sigh::Options.available_options, options)
    check_profile_option(configuration.fetch(:development, ask: false) == development,
                         "Wrong normalized development value for #{mode}")
    check_profile_option(configuration.fetch(:adhoc, ask: false) == adhoc,
                         "Wrong normalized adhoc value for #{mode}")
    check_profile_option(configuration.fetch(:developer_id, ask: false) == false,
                         "Developer ID must not be enabled for #{mode}")
  end

  # This is the exact parameter-shape regression from the failed candidate build.
  # Fastlane detects conflicting present keys even when both values are false.
  puts "Checking expected negative control: development:false plus adhoc:false"
  conflict = nil
  begin
    FastlaneCore::Configuration.create(Sigh::Options.available_options,
                                       { development: false, adhoc: false })
  rescue StandardError => error
    conflict = error
  end
  check_profile_option(conflict && conflict.message.include?("You can't enable both") &&
                       conflict.message.include?(":development") && conflict.message.include?(":adhoc"),
                       "Negative control did not reproduce the real Fastlane conflicting-options error")
  puts "Real Fastlane profile configuration: all 3 modes accepted; original conflicting-key regression rejected"
ensure
  saved_environment.each { |name, value| ENV[name] = value }
end
