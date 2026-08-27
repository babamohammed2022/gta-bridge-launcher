-- GTA Bridge Engine-Grade Performance Overlay
-- Builds memory_overlay.asi (x86) that hooks D3D9 EndScene for engine-debug overlay
solution "memory_overlay"
    configurations { "Release", "Debug" }
    platforms { "Win32" }
    location "build"
    targetdir "bin"
    implibdir "bin"

    staticruntime "On"
    rtti "Off"
    useimportlib "Off"
    buffersecuritycheck "Off"

    defines { "_CRT_SECURE_NO_WARNINGS", "_SCL_SECURE_NO_WARNINGS" }

    includedirs {
        ".",
        "../asi_bridge/src/shared",
        "../asi_bridge/src/shared/injector",
        "../asi_bridge/src/shared/structs",
    }

    filter "configurations:Debug*"
        symbols "On"
    filter "configurations:Release*"
        defines { "NDEBUG" }
        optimize "Speed"
    filter "action:vs*"
        buildoptions { "/arch:IA32" }
    filter {}

    project "memory_overlay"
        language "C++"
        kind "SharedLib"
        targetname "memory_overlay"
        targetextension ".asi"
        files {
            "memory_overlay.asi.cpp",
        }