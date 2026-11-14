# Adds the watchOS app (targets/watch) to the Xcode project that `one prebuild` generates.
# One's prebuild has no watch targets, so this runs after it; it is safe to run twice.
require 'xcodeproj'

ROOT = File.expand_path('..', __dir__)
PROJECT_PATH = File.join(ROOT, 'ios', 'MakoCapacity.xcodeproj')
APP_NAME = 'MakoCapacity'
WATCH_NAME = 'CapacityWatch'
BUNDLE_ID = 'dev.mako.capacity'

project = Xcodeproj::Project.open(PROJECT_PATH)
app = project.targets.find { |target| target.name == APP_NAME } or abort("#{APP_NAME} target not found; run one prebuild first")

if project.targets.any? { |target| target.name == WATCH_NAME }
  puts "#{WATCH_NAME} already present"
  exit 0
end

group = project.main_group.new_group(WATCH_NAME, '../targets/watch')
sources = [group.new_file('CapacityWatchApp.swift')]
assets = group.new_file('Assets.xcassets')

watch = project.new_target(:application, WATCH_NAME, :watchos, '10.0', nil, :swift)
watch.add_file_references(sources)
watch.add_resources([assets])
watch.build_configurations.each do |config|
  config.build_settings.merge!(
    'PRODUCT_NAME' => WATCH_NAME,
    'PRODUCT_BUNDLE_IDENTIFIER' => "#{BUNDLE_ID}.watchkitapp",
    'GENERATE_INFOPLIST_FILE' => 'YES',
    'INFOPLIST_KEY_CFBundleDisplayName' => 'Capacity',
    'INFOPLIST_KEY_WKCompanionAppBundleIdentifier' => BUNDLE_ID,
    'INFOPLIST_KEY_UISupportedInterfaceOrientations' => 'UIInterfaceOrientationPortrait UIInterfaceOrientationPortraitUpsideDown',
    'ASSETCATALOG_COMPILER_APPICON_NAME' => 'AppIcon',
    'TARGETED_DEVICE_FAMILY' => '4',
    'SWIFT_VERSION' => '5.0',
    'MARKETING_VERSION' => '1.0',
    'CURRENT_PROJECT_VERSION' => '1',
    'CODE_SIGN_STYLE' => 'Automatic',
    'SKIP_INSTALL' => 'YES',
    'ENABLE_PREVIEWS' => 'YES',
    'LD_RUNPATH_SEARCH_PATHS' => '$(inherited) @executable_path/Frameworks',
  )
end

app.add_dependency(watch)
embed = app.new_copy_files_build_phase('Embed Watch Content')
embed.dst_subfolder_spec = '16'
embed.dst_path = '$(CONTENTS_FOLDER_PATH)/Watch'
embed.add_file_reference(watch.product_reference).settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }

project.save

scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(watch)
scheme.set_launch_target(watch)
scheme.save_as(PROJECT_PATH, WATCH_NAME, true)
puts "#{WATCH_NAME} added and embedded in #{APP_NAME}"
