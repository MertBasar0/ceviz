# Secretless boundary test: load the real lane with Apple and Xcode actions replaced.
# Run with: ruby tests/fastlane_signing_test.rb
$signing_events = []
$ceviz_lanes = {}

module UI
  def self.message(_message); end
  def self.success(_message); end
  def self.user_error!(message)
    raise message
  end
end

module SharedValues
  SIGH_NAME = :sigh_name
  IPA_OUTPUT_PATH = :ipa_output_path
end

module Gym
  class PackageCommandGeneratorXcode7
    def self.config_path
      "/tmp/ceviz-generated-export.plist"
    end
  end
end

module Spaceship
  module ConnectAPI
    class BundleId
      Entry = Struct.new(:identifier) do
        def get_capabilities
          [Struct.new(:capability_type).new("PUSH_NOTIFICATIONS")]
        end
      end

      class << self
        attr_accessor :records, :fail_create

        def find(identifier)
          records[identifier]
        end

        def create(**attributes)
          $signing_events << [:create_bundle, attributes]
          return nil if fail_create

          records[attributes.fetch(:identifier)] = Entry.new(attributes.fetch(:identifier))
        end
      end
    end
  end
end

def default_platform(_name); end
def desc(_text); end
def lane(name, &block)
  $ceviz_lanes[name] = block
end
def platform(_name)
  yield
end
def lane_context
  @lane_context ||= {}
end
def get_provisioning_profile(**options)
  raise "Profile requested before bundle ID registration" unless Spaceship::ConnectAPI::BundleId.find(options.fetch(:app_identifier))
  $signing_events << [:profile, options]
  lane_context[SharedValues::SIGH_NAME] = "Installed #{options.fetch(:app_identifier)}"
end
def update_code_signing_settings(**options)
  $signing_events << [:signing, options]
end
def build_app(**options)
  $signing_events << [:build, options]
  lane_context[SharedValues::IPA_OUTPUT_PATH] = "fixture.ipa"
end
def app_store_connect_api_key(**options)
  $signing_events << [:asc_key, options]
  :test_api_key
end
def upload_to_testflight(**options)
  $signing_events << [:upload, options]
end
def check(condition, message)
  raise message unless condition
end

load File.expand_path("../fastlane/Fastfile", __dir__)
saved_team = ENV["TEAM_ID"]
saved_candidate = ENV["CEVIZ_DEVICE_CHECK_CANDIDATE"]
saved_capture = Open3.method(:capture3)
ENV["TEAM_ID"] = "TESTTEAM"

begin
  Spaceship::ConnectAPI::BundleId.records = SIGNING_TARGETS.values.reject { |bid| bid == WIDGET_BUNDLE_ID }.map do |bid|
    [bid, Spaceship::ConnectAPI::BundleId::Entry.new(bid)]
  end.to_h
  build_ceviz(:test_api_key, "app-store")
  ensure_widget_bundle_id

  registrations = $signing_events.select { |kind, _| kind == :create_bundle }.map(&:last)
  check(registrations == [{ identifier: WIDGET_BUNDLE_ID, name: "Ceviz Watch Voice Widget", platform: "IOS" }],
        "Widget registration must be exact and idempotent")

  profiles = $signing_events.select { |kind, _| kind == :profile }.map(&:last)
  check(profiles.map { |value| value.fetch(:app_identifier) } == SIGNING_TARGETS.values,
        "All three bundle IDs need their own profile")
  check(profiles.all? { |value| !value.key?(:development) && !value.key?(:adhoc) },
        "App Store profiles must omit both conflicting development/ad hoc options")

  signing = $signing_events.select { |kind, _| kind == :signing }.map(&:last)
  check(signing.length == 3, "Each target needs explicit archive signing")
  SIGNING_TARGETS.each do |target, bundle_id|
    settings = signing.find { |value| value.fetch(:targets) == [target] }
    check(settings && settings.fetch(:profile_name) == "Installed #{bundle_id}", "Profile mapped to wrong target")
    check(settings.fetch(:use_automatic_signing) == false, "Archive must not use automatic signing")
    check(settings.fetch(:code_sign_identity) == "Apple Distribution", "Archive must use the imported distribution identity")
    check(settings.fetch(:build_configurations) == ["Release"], "Only archive configuration should change")
  end

  archive = $signing_events.last
  check(archive.first == :build, "Signing must finish before archive starts")
  check(archive.last.fetch(:xcargs).match?(/\ACURRENT_PROJECT_VERSION=\d+\z/),
        "Archive must not create certificates through automatic provisioning")
  check(archive.last.fetch(:export_options).fetch(:provisioningProfiles).keys == SIGNING_TARGETS.values,
        "Export must retain the same complete profile mapping")

  { "development" => { development: true }, "ad-hoc" => { adhoc: true } }.each do |method, expected|
    $signing_events.clear
    provision(:test_api_key, method)
    requested = $signing_events.select { |kind, _| kind == :profile }.map(&:last)
    check(requested.length == 3, "Every mode must provision all three targets")
    check(requested.all? { |value| value.select { |key, _| [:development, :adhoc].include?(key) } == expected },
          "Provisioning must pass only the selected mode flag")
  end
  previous_profiles = $signing_events.length
  begin
    provision(:test_api_key, "unknown")
    raise "Unknown provisioning modes must stop before a profile request"
  rescue RuntimeError => error
    raise unless error.message == "Unsupported Ceviz provisioning method: unknown"
  end
  check($signing_events.length == previous_profiles, "Unknown modes must not request profiles")

  native_help = "Available keys for -exportOptionsPlist:\n\ttestFlightInternalTestingOnly : Bool\n\tRestrict distribution to internal TestFlight testing.\n"
  help_success = true
  export_value = "true\n"
  export_success = true
  command_status = Struct.new(:success?)
  Open3.define_singleton_method(:capture3) do |*command|
    $signing_events << [:native, command]
    case command
    when ["xcodebuild", "-help"]
      [native_help, "", command_status.new(help_success)]
    when ["/usr/libexec/PlistBuddy", "-c", "Print :testFlightInternalTestingOnly", Gym::PackageCommandGeneratorXcode7.config_path]
      [export_value, "", command_status.new(export_success)]
    else
      raise "Unexpected native command: #{command.inspect}"
    end
  end

  [nil, "false", "true"].each do |candidate|
    $signing_events.clear
    ENV["CEVIZ_DEVICE_CHECK_CANDIDATE"] = candidate
    $ceviz_lanes.fetch(:beta).call
    archive = $signing_events.find { |kind, _| kind == :build }.last
    options = archive.fetch(:export_options)
    if candidate == "true"
      check(options[:testFlightInternalTestingOnly] == true, "Candidate archive must be Internal Only")
      kinds = $signing_events.map(&:first)
      check(kinds.index(:native) < kinds.index(:profile), "Native support must be verified before signing requests")
      check(kinds.last(3) == [:build, :native, :upload], "Generated export must be verified after archive and before upload")
    else
      check(!options.key?(:testFlightInternalTestingOnly), "Normal export must not acquire a candidate restriction")
      check($signing_events.none? { |kind, _| kind == :native }, "Normal export must not depend on candidate probes")
    end
    upload = $signing_events.last
    check(upload == [:upload, { api_key: :test_api_key, skip_waiting_for_build_processing: true,
                               skip_submission: true, distribute_external: false,
                               notify_external_testers: false, ipa: "fixture.ipa" }],
          "Beta lane must upload only the produced IPA without group assignment or external distribution")
  end

  ENV["CEVIZ_DEVICE_CHECK_CANDIDATE"] = "true"
  [[:help_missing, "", true, "true\n", true, false],
   [:help_failed, native_help, false, "true\n", true, false],
   [:export_false, native_help, true, "false\n", true, true],
   [:export_missing, native_help, true, "", false, true]].each do |name, help, help_ok, value, export_ok, archived|
    $signing_events.clear
    native_help, help_success, export_value, export_success = help, help_ok, value, export_ok
    begin
      $ceviz_lanes.fetch(:beta).call
      raise "Candidate upload must stop for #{name}"
    rescue RuntimeError => error
      expected = archived ? "Generated export is not Internal Only; upload stopped" : "Selected Xcode does not advertise the internal-only export contract"
      raise unless error.message == expected
    end
    check($signing_events.none? { |kind, _| kind == :upload }, "Failed #{name} must not upload")
    check($signing_events.any? { |kind, _| kind == :build } == archived, "Failed #{name} stopped at wrong boundary")
    check(archived || $signing_events.none? { |kind, _| kind == :profile }, "Failed native contract must not request signing profiles")
  end

  $signing_events.clear
  ENV["CEVIZ_DEVICE_CHECK_CANDIDATE"] = "maybe"
  begin
    $ceviz_lanes.fetch(:beta).call
    raise "Unknown candidate mode must stop"
  rescue RuntimeError => error
    raise unless error.message == "Device-check candidate must be explicitly true or false"
  end
  check($signing_events.empty?, "Invalid candidate mode must stop before Apple or build actions")

  Spaceship::ConnectAPI::BundleId.records.delete(WIDGET_BUNDLE_ID)
  Spaceship::ConnectAPI::BundleId.fail_create = true
  previous_archives = $signing_events.count { |kind, _| kind == :build }
  begin
    build_ceviz(:test_api_key, "app-store")
    raise "Failed widget registration must stop the build"
  rescue RuntimeError => error
    raise unless error.message == "Could not register Ceviz Watch widget bundle ID"
  end
  check($signing_events.count { |kind, _| kind == :build } == previous_archives,
        "No archive is allowed after failed widget registration")

  puts "Fastlane signing boundary tests passed"
ensure
  ENV["TEAM_ID"] = saved_team
  ENV["CEVIZ_DEVICE_CHECK_CANDIDATE"] = saved_candidate
  Open3.define_singleton_method(:capture3, saved_capture)
end
