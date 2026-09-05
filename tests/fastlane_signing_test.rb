# Secretless boundary test: load the real lane with Apple and Xcode actions replaced.
# Run with: ruby tests/fastlane_signing_test.rb
$signing_events = []

module UI
  def self.message(_message); end
  def self.success(_message); end
  def self.user_error!(message)
    raise message
  end
end

module SharedValues
  SIGH_NAME = :sigh_name
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
def lane(_name); end
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
end
def check(condition, message)
  raise message unless condition
end

load File.expand_path("../fastlane/Fastfile", __dir__)
saved_team = ENV["TEAM_ID"]
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
end
